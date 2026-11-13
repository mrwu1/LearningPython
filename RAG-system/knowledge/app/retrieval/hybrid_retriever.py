import json
import os
import re
import time
from contextlib import contextmanager
from typing import Optional, Dict, Any, List, Literal

import jieba
from pydantic import BaseModel, Field

from app.db.connection import get_db_connection
from app.cache.redis_cache import RedisCacheManager
from app.indexing.embedding_service import EmbeddingService
from loguru import logger

from app.retrieval.reranker import ZhipuReranker


class RetrievedChunk(BaseModel):
    """单条召回片段的标准数据结构"""
    chunk_id: int
    file_id: int
    file_name: str
    chunk_index: int
    content: str
    score: float = Field(
        description="当前检索模式下的主排序得分（加权RRF得分 / 余弦相似度 / 全文密度分 / 重排分）"
    )
    dense_score: Optional[float] = Field(
        default=None,
        description="向量余弦相似度 [0, 1]"
    )
    sparse_score: Optional[float] = Field(
        default=None,
        description="全文覆盖密度得分 ts_rank_cd"
    )
    # ✅ 新
    rerank_score: Optional[float] = Field(default=None, description="Cross-Encoder 重排模型深度语义分 [0, 1]")  # 👈
    rank_d:Optional[int] = Field(
        default=None,
        description="向量检索路内名次"
    )
    rank_s:Optional[int] = Field(
        default=None,
        description="全文检索路内名次"
    )
    metadata:Dict[str,Any] = Field(
        default_factory=dict, ## 所有的实例都会共用这个 {}
    )
class HybridRetriever:
    """
    PostgreSQL 单引擎混合检索器：
    支持 dense(HNSW向量)，sparse(GIN全文倒排)，hybrid(CTE RRF倒数秩融合) 三种模式
    """
    def __init__(
            self,
            embedder:EmbeddingService|None = None,
            reranker: Optional[ZhipuReranker] = None,  # 👈 1. 入参允许外部注入自定义重排器
            rrf_k:int=60,
            recall_k:int=20,
            dense_weight: float = 0.7,
            sparse_weight: float = 0.3,
            max_chunks_per_file: int = 2,
    ):
        self.embedder = embedder or EmbeddingService()
        self.reranker = reranker or ZhipuReranker()  # 👈 2. 挂载到 self.reranker 实例属性上！
        self.rrf_k = rrf_k  # RRF 平滑常数 k (标准值 60)
        self.recall_k = recall_k # 单路初始召回窗口大小 (默认 Top-20)
        self.dense_weight = dense_weight  # 向量检索权重 (默认 0.7)
        self.sparse_weight = sparse_weight  # 全文检索权重 (默认 0.3)
        self.max_chunks_per_file = max_chunks_per_file  # 同文档最多保留切片数 (默认 2，根治霸榜)

        self.cache = RedisCacheManager()

    def _get_connection(self):
        """复用全局统一数据库连接池上下文管理器"""
        return get_db_connection()

    @staticmethod
    def _build_tsquery(query:str)->str:
        """
        将用户的问题经 jieba 搜索模式分词，清洗特殊符号后拼接为  '词1 | 词2 | 词3'
        """
        raw_words = jieba.cut_for_search(query)
        clean_tokens = []
        for w in raw_words:
            w = w.strip()
            # 仅保留中英文与数字，过滤掉可能破坏 to_tsquery 语法的标点与操作符
            if w and re.match(r"^[\u4e00-\u9fa5a-zA-Z0-9]+$", w):
                if w not in clean_tokens:
                    clean_tokens.append(w)
        return " | ".join(clean_tokens)

    @staticmethod
    def _parse_metadata(raw_meta: Any) -> Dict[str, Any]:
        if isinstance(raw_meta, dict):
            return raw_meta
        if isinstance(raw_meta, str) and raw_meta.strip():
            try:
                return json.loads(raw_meta)
            except Exception:
                return {}
        return {}

    def search_dense(self,query:str,top_k:int=5,query_vec_str:str|None=None)->List[RetrievedChunk]:
        """
        模式一：纯向量搜索 Dense Search
        """
        if not query_vec_str:
            vec = self.embedder.embedding_query(query)
            query_vec_str = str(vec)
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql="""
                    select 
                        kc.id as chunk_id,
                        kc.file_id,
                        kc.chunk_index,
                        kc.content,
                        kc.metadata,
                        1 - (kc.embedding <=>%s::vector )  as dense_score,
                        row_number() over(order by kc.embedding <=>%s::vector asc) as rank_d
                    from kb.kb_chunk kc
                    join kb.kb_file kf on kf.id = kc.file_id
                    where kf.delete_flag = FALSE
                    order by kc.embedding <=>%s::vector asc
                    limit %s;
                """
                cursor.execute(sql,(query_vec_str,query_vec_str,query_vec_str, top_k))
                rows = cursor.fetchall()
        results=[]
        for r in rows:
            cid, fid, c_idx, content, raw_meta, d_score, rank_d = r
            meta = self._parse_metadata(raw_meta)
            results.append(
                RetrievedChunk(
                    chunk_id=cid,
                    file_id=int(fid),
                    file_name=meta.get("file_name", "未知制度"),
                    chunk_index=c_idx,
                    content=content,
                    score=round(float(d_score), 6),
                    dense_score=round(float(d_score), 6),
                    sparse_score=None,
                    rank_d=int(rank_d),
                    rank_s=None,
                    metadata=meta,
                )
            )
        return results

    def search_sparse(self,query:str,top_k:int=5,tsquery_str:str|None=None)->List[RetrievedChunk]:
        """模式2: 纯全文倒排检索（sparse search）"""
        if tsquery_str is None:
            tsquery_str = self._build_tsquery(query)
        if not tsquery_str:
            logger.warning(f"[Retriever] 提问未提取到有效分词，跳过全文检索: {query}")
            return []
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql="""
                select 
                    kc.id as chunk_id,
                    kc.file_id,
                    kc.chunk_index,
                    kc.content,
                    kc.metadata,
                    ts_rank_cd(kc.tsv_content, to_tsquery('simple', %s)) as sparse_score,
                    row_number() over(order by ts_rank_cd(kc.tsv_content, to_tsquery('simple', %s)) desc) as rank_s
                from kb.kb_chunk kc 
                join kb.kb_file kf on kf.id = kc.file_id
                where kf.delete_flag = FALSE
                    and kc.tsv_content @@ to_tsquery('simple', %s)
                ORDER BY sparse_score DESC
                limit %s;
                """
                cursor.execute(sql,(tsquery_str,tsquery_str,tsquery_str,top_k))
                rows = cursor.fetchall()
        results = []
        for r in rows:
            cid, fid, c_idx, content, raw_meta, s_score, rank_s = r
            meta = self._parse_metadata(raw_meta)
            results.append(
                RetrievedChunk(
                    chunk_id=cid,
                    file_id=int(fid),
                    file_name=meta.get("file_name", "未知制度"),
                    chunk_index=c_idx,
                    content=content,
                    score=round(float(s_score), 6),
                    dense_score=None,
                    sparse_score=round(float(s_score), 6),
                    rank_d=None,
                    rank_s=int(rank_s),
                    metadata=meta,
                )
            )
        return results
    def search_hybrid(self,query:str,top_k:int=5)->List[RetrievedChunk]:
        """
        模式3: 加权RRF + 同文档窗口折叠限流混合检索（Production Document Collapse)
        """
        tsquery_str = self._build_tsquery(query)  # jieba | 次 ｜ 词
        vec = self.embedder.embedding_query(query)  # [0.123, 0.456, 0.789]
        query_vec_str = str(vec)  # "[0.123, 0.456, 0.789]"
        if not tsquery_str:
            logger.warning(f"[Retriever] 全文分词为空，自动降级为 Dense 向量检索: {query}")
            return self.search_dense(query, top_k=top_k, query_vec_str=query_vec_str)
        # 初始召回缓冲池大小：至少捞出 top_k * 4，确保去重后依然有足够的切片参选
        recall_limit = max(self.recall_k,top_k*4)
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql="""
                WITH dense_results AS (
                            SELECT
    				kc.id,
    				1 - (kc.embedding <=> %s::vector) AS dense_score,
    				row_number() OVER (ORDER BY kc.embedding <=> %s::vector ASC) AS rank_d
                            FROM kb.kb_chunk kc
                            JOIN kb.kb_file kf ON kf.id = kc.file_id
                            WHERE kf.delete_flag = FALSE
                            ORDER BY kc.embedding <=> %s::vector ASC
                            LIMIT %s
    			),
    			sparse_results AS (
                            SELECT
    				kc.id,
    				ts_rank_cd(kc.tsv_content, to_tsquery('simple', %s)) AS sparse_score,
    				row_number() OVER (ORDER BY ts_rank_cd(kc.tsv_content, to_tsquery('simple', %s)) DESC) AS
    				rank_s
                            FROM kb.kb_chunk kc
                            JOIN kb.kb_file kf ON kf.id = kc.file_id
                            WHERE kf.delete_flag = FALSE
                              AND kc.tsv_content @@ to_tsquery('simple', %s)
                            ORDER BY sparse_score DESC
                            LIMIT %s
    			),
    			rrf_fused AS (
                            SELECT
    				coalesce(d.id, s.id) AS chunk_id,
    				d.dense_score,
    				d.rank_d,
    				s.sparse_score,
    				s.rank_s,
    				(
                                    coalesce(%s / (%s + d.rank_d), 0.0) +
                                    coalesce(%s / (%s + s.rank_s), 0.0)
    				) AS rrf_score
                            FROM dense_results d
  				    FULL OUTER JOIN sparse_results s ON d.id = s.id
			    ),
                ranked_diversity AS (
                            SELECT 
                                c.id AS chunk_id,
                                c.file_id,
                                c.chunk_index, 
                                c.content,
  				                c.metadata,
  		                        r.rrf_score, 
                                r.dense_score,
  		                        r.sparse_score,
				                r.rank_d,
                                r.rank_s,
                                -- 生产核心：按文件分组打上组内名次，彻底粉碎单文档多切片霸榜效应                        
    				            row_number() OVER (
                                    PARTITION BY c.file_id 
                                    ORDER BY r.rrf_score DESC ) AS doc_chunk_rank
                            FROM rrf_fused r
                            JOIN kb.kb_chunk c ON r.chunk_id = c.id
    			)
    			SELECT 
                            chunk_id,
                            file_id,
                            chunk_index,
                            content,
                            metadata,
                            rrf_score,
                            dense_score,
                            sparse_score,
                            rank_d,
                            rank_s
    			FROM ranked_diversity
    			WHERE doc_chunk_rank <= %s
    			ORDER BY rrf_score DESC
    			LIMIT %s;
                """
                cursor.execute(sql, (
                    # 1. dense_results (4 个占位符)
                    query_vec_str, query_vec_str, query_vec_str, recall_limit,
                    # 2. sparse_results (4 个占位符)
                    tsquery_str, tsquery_str, tsquery_str, recall_limit,
                    # 3. rrf_fused (4 个占位符: dense_weight, rrf_k, sparse_weight, rrf_k)
                    self.dense_weight, self.rrf_k,
                    self.sparse_weight, self.rrf_k,
                    # 4. ranked_diversity 过滤与最终截断 (2 个占位符)
                    self.max_chunks_per_file,
                    top_k,
                ))
                rows = cursor.fetchall()
        results = []
        for r in rows:
            cid, fid, c_idx, content, raw_meta, rrf_score, d_score, s_score, rank_d, rank_s = r
            meta = self._parse_metadata(raw_meta)
            results.append(
                RetrievedChunk(
                    chunk_id=cid,
                    file_id=int(fid),
                    file_name=meta.get("file_name", "未知制度"),
                    chunk_index=c_idx,
                    content=content,
                    score=round(float(rrf_score), 6),
                    dense_score=round(float(d_score), 6) if d_score is not None else None,
                    sparse_score=round(float(s_score), 6) if s_score is not None else None,
                    rank_d=int(rank_d) if rank_d is not None else None,
                    rank_s=int(rank_s) if rank_s is not None else None,
                    metadata=meta,
                )
            )
        return results


    def search_hybrid_old(self,query:str,top_k:int=5)->List[RetrievedChunk]:
        """
        模式3: RRF 混合检索 (Dense + Sparse -> Reciprocal Rank Fusion)
        """
        tsquery_str = self._build_tsquery(query) #jieba | 次 ｜ 词
        vec = self.embedder.embedding_query(query)#[0.123, 0.456, 0.789]
        query_vec_str = str(vec) # "[0.123, 0.456, 0.789]"
        #1.如果没有关键词，降级为纯 dense search
        if not tsquery_str:
            logger.warning(f"[Retriever] 全文分词为空，自动降级为 Dense 向量检索: {query}")
            return self.search_dense(query, top_k=top_k, query_vec_str=query_vec_str)
        # ✅多捞一倍（2 倍）出来作为“缓冲池”，过滤掉垃圾后，还能保证有足够的数量给大模型。
        recall_limit = max(self.recall_k,top_k*2)

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    with dense_results as (
                        select
                            kc.id,
                            1 - (kc.embedding <=> %s::vector) as dense_score,
                            row_number() over(order by kc.embedding <=> %s::vector asc) as rank_d
                        from kb.kb_chunk kc
                        join kb.kb_file kf on kf.id = kc.file_id
                        where kf.delete_flag = FALSE
                        order by kc.embedding <=> %s::vector asc
                        limit %s
                    ),
                    sparse_results as (
                        select
                            kc.id,
                            ts_rank_cd(kc.tsv_content, to_tsquery('simple', %s)) as sparse_score,
                            row_number() over(order by ts_rank_cd(kc.tsv_content, to_tsquery('simple', %s)) desc) as rank_s
                        from kb.kb_chunk kc
                        join kb.kb_file kf on kf.id = kc.file_id
                        where kf.delete_flag = FALSE
                          and kc.tsv_content @@ to_tsquery('simple', %s)
                        order by sparse_score DESC
                        limit %s
                    ),
                    rrf_fused as (
                        select
                            coalesce(d.id, s.id) as chunk_id,
                            d.dense_score,
                            d.rank_d,
                            s.sparse_score,
                            s.rank_s,
                            (
                                coalesce(1.0 / (%s + d.rank_d), 0.0) +
                                coalesce(1.0 / (%s + s.rank_s), 0.0)
                            ) as rrf_score
                        from dense_results d
                        full outer join sparse_results s on d.id = s.id
                    )
                    select 
                        c.id AS chunk_id,
                        c.file_id,
                        c.chunk_index,
                        c.content,
                        c.metadata,
                        r.rrf_score,
                        r.dense_score,
                        r.sparse_score,
                        r.rank_d,
                        r.rank_s 
                    from rrf_fused r
                    join kb.kb_chunk c on r.chunk_id = c.id
                    order by r.rrf_score desc
                    limit %s;
                """
                cursor.execute(sql,(
                    query_vec_str, query_vec_str, query_vec_str, recall_limit,
                    tsquery_str, tsquery_str, tsquery_str, recall_limit,
                    self.rrf_k, self.rrf_k,
                    top_k,
                ))
                rows = cursor.fetchall()
        results = []
        for r in rows:
            cid, fid, c_idx, content, raw_meta, rrf_score, d_score, s_score, rank_d, rank_s = r
            meta = self._parse_metadata(raw_meta)
            results.append(
                RetrievedChunk(
                    chunk_id=cid,
                    file_id=int(fid),
                    file_name=meta.get("file_name", "未知制度"),
                    chunk_index=c_idx,
                    content=content,
                    score=round(float(rrf_score), 6),
                    dense_score=round(float(d_score), 6) if d_score is not None else None,
                    sparse_score=round(float(s_score), 6) if s_score is not None else None,
                    rank_d=int(rank_d) if rank_d is not None else None,
                    rank_s=int(rank_s) if rank_s is not None else None,
                    metadata=meta,
                )
            )
        return results

    def retrieve(
            self,
            query:str,
            top_k:int=5,
            mode: Literal["hybrid","dense","sparse"]='hybrid',
            use_cache:bool=True,
            use_rerank: bool = True,  # 👈 允许通过传参控制是否启用重排
    )->List[RetrievedChunk]:
        """统一检索路由入口（带 L2 检索缓存加速）"""
        start_time = time.perf_counter()
        # 1.尝试读取L2检索结果缓存
        if use_cache:
            cache_items = self.cache.get_retrieval(query=query,mode=mode, top_k=top_k)
            if cache_items is not None:
                res = [RetrievedChunk(**item) for item in cache_items]
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[Retriever-CacheHit] 模式={mode} | Top-{top_k} | 命中={len(res)}条 | 耗时={elapsed_ms:.2f}ms")
                return res
        # 2. 第一阶段：粗排检索（若启用重排，粗排窗口扩大至 top_k * 4，确保候选丰富）
        coarse_limit = max(self.recall_k, top_k * 4) if use_rerank else top_k

        # 2. 缓存未命中，执行数据库检索
        if mode == "dense":
            coarse_candidates = self.search_dense(query, top_k=coarse_limit)
        elif mode == "sparse":
            coarse_candidates = self.search_sparse(query, top_k=coarse_limit)
        else:
            coarse_candidates = self.search_hybrid(query, top_k=coarse_limit)

        # 3. 第二阶段：调用重排器精排（带生产级降级保护）
        if use_rerank and coarse_candidates and self.reranker:
            try:
                # 提取候选切片内容送入 Cross-Encoder
                doc_texts = [c.content for c in coarse_candidates]
                # 👈 核心调用：
                rerank_results = self.reranker.rerank(query=query, documents=doc_texts, top_n=top_k)

                final_chunks: List[RetrievedChunk] = []
                for item in rerank_results:
                    idx = item["index"]
                    score = item["relevance_score"]
                    chunk = coarse_candidates[idx]
                    chunk.rerank_score = round(score, 6)
                    chunk.score = round(score, 6)  # 把主排序分替换为重排分  ‼️
                    final_chunks.append(chunk)

                res = final_chunks
            except Exception as e:
                # 生产防御：重排接口报错或超时，自动降级回退粗排
                logger.warning(f"[Retriever] 重排阶段触发降级，回退至粗排排序: {e}")
                res = coarse_candidates[:top_k]
        else:
            res = coarse_candidates[:top_k]


        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"[Retriever] 模式={mode} | Top-{top_k} | 命中={len(res)}条 | 耗时={elapsed_ms:.1f}ms | Query='{query}'")
        # 3. 将检索结果序列化回写至 L2 缓存
        self.cache.set_retrieval(
            query=query,
            mode=mode,
            top_k=top_k,
            chunks_data=[c.model_dump() for c in res]
        )
        return res

