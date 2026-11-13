"""
受控批量摄取执行引擎 (Batch Ingest Executor)
负责全量语料或特定类型分组的受控跑批，集成结构化切片与全局看板统计。
统一复用全局数据库连接池 get_db_connection。
"""
import os
import json
import traceback
from typing import Optional, List, Dict, Any
from psycopg2.extras import execute_batch
from loguru import logger
from pydantic import BaseModel, Field

from app.db.connection import get_db_connection
from app.parsers.document_parser import DocumentParser, ParseResult
from app.indexing.embedding_service import EmbeddingService
from app.cache.redis_cache import RedisCacheManager


class SingleFileResult(BaseModel):
    file_id: int
    file_name: str
    status: str
    chunk_count: int = 0
    error_message: Optional[str] = None


class BatchExecutionResult(BaseModel):
    batch_size: int
    processed_count: int
    success_count: int
    failed_count: int
    remaining_pending: int
    details: List[SingleFileResult] = Field(default_factory=list)


class BatchExecutor:
    """受控批量摄取执行器"""

    def __init__(
        self,
        parser: Optional[DocumentParser] = None,
        embedder: Optional[EmbeddingService] = None,
    ):
        self.parser = parser or DocumentParser()
        self.embedder = embedder or EmbeddingService()
        self.cache = RedisCacheManager()

    def process_single_file(self, file_record: Dict[str, Any]) -> SingleFileResult:
        """
        单文件执行管道：
        1. 状态置为 PROCESSING (短事务立即提交，通知其他线程已占用)
        2. 事务外执行耗时的网络下载、文本解析、结构化切片与向量化计算 (释放 DB 连接，杜绝长事务占用)
        3. 短事务批量落库切片与向量，更新状态为 COMPLETED
        """
        file_id = file_record["id"]
        file_name = file_record["name"]
        url = file_record["url"]
        file_ext = file_record["file_ext"]

        # 1. 短事务置为 PROCESSING
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE kb.kb_file SET status = 'PROCESSING', error_message = NULL WHERE id = %s;",
                    (file_id,)
                )
                conn.commit()

        try:
            # 2. 事务外执行耗时的网络下载、文本解析与多模态切片
            parse_res: ParseResult = self.parser.parse_from_cos(
                url=url,
                file_name=file_name,
                file_id=file_id,
                file_ext=file_ext,
            )

            if not parse_res.chunks:
                with get_db_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE kb.kb_file SET status = 'COMPLETED', chunk_count = 0, error_message = NULL, indexed_at = CURRENT_TIMESTAMP WHERE id = %s;",
                            (file_id,),
                        )
                        conn.commit()
                return SingleFileResult(
                    file_id=file_id,
                    file_name=file_name,
                    status="COMPLETED",
                    chunk_count=0,
                )

            # 3. 事务外批量计算 1024 维稠密向量
            chunk_texts = [c.content for c in parse_res.chunks]
            embeddings = self.embedder.embed_document(chunk_texts)

            # 4. 短事务幂等写入新切片
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM kb.kb_chunk WHERE file_id = %s;", (file_id,))
                    insert_sql = """
                        INSERT INTO kb.kb_chunk
                        (file_id, chunk_index, content, token_count, metadata, embedding, tsv_content)
                        VALUES (%s, %s, %s, %s, %s, %s, to_tsvector('simple', %s));
                    """
                    batch_records = []
                    for chunk, emb in zip(parse_res.chunks, embeddings):
                        batch_records.append((
                            file_id,
                            chunk.chunk_index,
                            chunk.content,
                            chunk.token_count,
                            json.dumps(chunk.metadata, ensure_ascii=False),
                            emb,
                            chunk.jieba_tokens
                        ))
                    execute_batch(cursor, insert_sql, batch_records, page_size=100)

                    cursor.execute(
                        """
                        UPDATE kb.kb_file
                        SET status = 'COMPLETED', chunk_count = %s, error_message = NULL, indexed_at = CURRENT_TIMESTAMP
                        WHERE id = %s;
                        """,
                        (len(parse_res.chunks), file_id),
                    )
                    conn.commit()

            logger.info(f"✅ 文件成功入库: {file_name} (ID: {file_id}, 生成切片: {len(parse_res.chunks)})")
            return SingleFileResult(
                file_id=file_id,
                file_name=file_name,
                status="COMPLETED",
                chunk_count=len(parse_res.chunks),
            )

        except Exception as e:
            error_stack = traceback.format_exc()
            logger.error(f"❌ 文件处理失败: {file_name} (ID: {file_id}) | 错误: {e}")
            try:
                with get_db_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE kb.kb_file SET status = 'FAILED', error_message = %s WHERE id = %s;",
                            (error_stack, file_id),
                        )
                        conn.commit()
            except Exception as update_err:
                logger.error(f"更新失败状态失败: {update_err}")

            return SingleFileResult(
                file_id=file_id,
                file_name=file_name,
                status="FAILED",
                chunk_count=0,
                error_message=str(e),
            )

    @staticmethod
    def _build_ext_condition(ext_filter: str):
        """解析文件类型分组过滤表达式"""
        ef = ext_filter.lower().strip().lstrip(".")
        if ef in ["image", "img", "pic", "ocr"]:
            return "LOWER(file_ext) IN ('jpg', 'jpeg', 'png', 'bmp', 'webp')", []
        elif ef in ["word"]:
            return "LOWER(file_ext) IN ('docx', 'doc')", []
        elif ef in ["excel"]:
            return "LOWER(file_ext) IN ('xlsx', 'xls')", []
        elif ef in ["ppt", "presentation"]:
            return "LOWER(file_ext) IN ('pptx', 'ppt')", []
        else:
            return "LOWER(file_ext) = %s", [ef]

    def process_file_by_id(self, file_id: int | str) -> SingleFileResult:
        """精确处理单份文件：清空旧切片、重置状态并立即解析入库"""
        fid = int(file_id)
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, name, url, file_ext, file_type FROM kb.kb_file WHERE id = %s AND delete_flag = FALSE;",
                    (fid,),
                )
                row = cursor.fetchone()
                if not row:
                    raise ValueError(f"未找到 ID 为 {fid} 的有效文件记录")

                file_item = {"id": row[0], "name": row[1], "url": row[2], "file_ext": row[3], "file_type": row[4]}
                cursor.execute("DELETE FROM kb.kb_chunk WHERE file_id = %s;", (fid,))
                cursor.execute("UPDATE kb.kb_file SET status = 'PROCESSING', error_message = NULL WHERE id = %s;", (fid,))
                conn.commit()

        res = self.process_single_file(file_item)
        if res.status == "COMPLETED":
            self.cache.bump_corpus_version()
        return res

    def execute_batch(
        self,
        batch_size: int = 5,
        file_ext: Optional[str] = None,
        file_ids: Optional[List[int | str]] = None,
    ) -> BatchExecutionResult:
        """
        受控批次调度主入口：
        支持全局拉取、按文件类型分组拉取 (file_ext)、或精确批量指定 (file_ids)
        使用 FOR UPDATE SKIP LOCKED 原子拉取待办文件并依次执行
        """
        where_clauses = ["delete_flag = FALSE"]
        params: List[Any] = []

        if file_ids and len(file_ids) > 0:
            int_ids = [int(x) for x in file_ids]
            where_clauses.append("id = ANY(%s)")
            params.append(int_ids)
            limit_val = len(int_ids)
        else:
            where_clauses.append("status IN ('PENDING', 'FAILED')")
            if file_ext and file_ext.upper() != "ALL":
                cond, ext_params = self._build_ext_condition(file_ext)
                where_clauses.append(cond)
                params.extend(ext_params)
            limit_val = batch_size

        where_sql = " AND ".join(where_clauses)
        params.append(limit_val)

        fetch_sql = f"""
            SELECT id, name, url, file_ext, file_type
            FROM kb.kb_file
            WHERE {where_sql}
            ORDER BY id ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED;
        """

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(fetch_sql, tuple(params))
                rows = cursor.fetchall()
                logger.info(
                    f"sql执行结果：{len(rows)} (过滤条件: file_ext={file_ext}, file_ids count={len(file_ids) if file_ids else 0})"
                )
                pending_files = [
                    {"id": r[0], "name": r[1], "url": r[2], "file_ext": r[3], "file_type": r[4]}
                    for r in rows
                ]
                conn.commit()

        if not pending_files:
            logger.info("未检测到待处理文件。")
            return BatchExecutionResult(
                batch_size=batch_size,
                processed_count=0,
                success_count=0,
                failed_count=0,
                remaining_pending=self.get_pending_count(),
                details=[]
            )

        logger.info(f"🚀 开始执行批次调度，本批次锁定文件数: {len(pending_files)}")
        results = []
        for file_item in pending_files:
            single_res = self.process_single_file(file_item)
            results.append(single_res)

        remaining_count = self.get_pending_count()
        success_cnt = sum(1 for r in results if r.status == "COMPLETED")
        if success_cnt > 0:
            self.cache.bump_corpus_version()

        failed_cnt = sum(1 for r in results if r.status == "FAILED")
        return BatchExecutionResult(
            batch_size=batch_size,
            processed_count=len(results),
            success_count=success_cnt,
            failed_count=failed_cnt,
            remaining_pending=remaining_count,
            details=results
        )

    def get_pending_count(self) -> int:
        """获取当前全库剩余 PENDING 数量"""
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM kb.kb_file WHERE status = 'PENDING' AND delete_flag = FALSE;"
                )
                return cursor.fetchone()[0]

    def reset_failed_files(self) -> int:
        """一键将所有 FAILED 状态文件重置为 PENDING"""
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE kb.kb_file SET status = 'PENDING', error_message = NULL WHERE status = 'FAILED';"
                )
                affected = cursor.rowcount
                conn.commit()
                logger.info(f"已将 {affected} 个 FAILED 文件重置为 PENDING。")
                return affected

    def get_overview_metrics(self) -> Dict[str, Any]:
        """单次扫描聚合计算全局看板指标"""
        sql = """
            SELECT count(*) as total_files,
                   COUNT(*) filter (where status='COMPLETED') as completed_files,
                   COUNT(*) FILTER (WHERE status = 'PENDING') AS pending_files,
                   COUNT(*) FILTER (WHERE status = 'PROCESSING') AS processing_files,
                   COUNT(*) FILTER (WHERE status = 'FAILED') AS failed_files,
                   COALESCE(SUM(chunk_count), 0) AS total_chunks
            FROM kb.kb_file
            WHERE delete_flag = FALSE;
        """
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                row = cursor.fetchone()
                total = row[0] or 0
                completed = row[1] or 0
                pending = row[2] or 0
                processing = row[3] or 0
                failed = row[4] or 0
                total_chunks = row[5] or 0
                progress = round(((completed + failed) / total * 100.0), 1) if total > 0 else 0.0
                return {
                    "total_files": total,
                    "completed_files": completed,
                    "pending_files": pending,
                    "processing_files": processing,
                    "failed_files": failed,
                    "total_chunks": total_chunks,
                    "progress_percent": progress,
                }

    def get_files_paginated(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 15,
        file_ext: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页查询文件状态列表，支持按状态筛选与按文件类型分组筛选，并附带格式分布统计"""
        offset = (page - 1) * page_size
        params: List[Any] = []
        where_clauses = ["delete_flag = FALSE"]

        if status and status.upper() != "ALL":
            where_clauses.append("status = %s")
            params.append(status.upper())

        if file_ext and file_ext.upper() != "ALL":
            cond, ext_p = self._build_ext_condition(file_ext)
            where_clauses.append(cond)
            params.extend(ext_p)

        where_sql = " AND ".join(where_clauses)

        list_sql = f"""
            SELECT id, name, file_ext, file_type, status, chunk_count, error_message, create_time, indexed_at
            FROM kb.kb_file
            WHERE {where_sql}
            ORDER BY 
                CASE status 
                    WHEN 'PROCESSING' THEN 1 
                    WHEN 'FAILED' THEN 2 
                    WHEN 'PENDING' THEN 3
                    WHEN 'COMPLETED' THEN 4 
                    ELSE 5 
                END,
                id ASC
            LIMIT %s OFFSET %s;
        """

        stat_sql = """
            SELECT LOWER(file_ext) AS ext,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'PENDING') AS pending,
                   COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed,
                   COUNT(*) FILTER (WHERE status = 'FAILED') AS failed
            FROM kb.kb_file
            WHERE delete_flag = FALSE
            GROUP BY LOWER(file_ext)
            ORDER BY total DESC;
        """

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) FROM kb.kb_file WHERE {where_sql};", tuple(params))
                total_count = cursor.fetchone()[0]

                cursor.execute(list_sql, tuple(params + [page_size, offset]))
                rows = cursor.fetchall()
                items = []
                for r in rows:
                    items.append({
                        "id": str(r[0]),
                        "name": r[1],
                        "file_ext": r[2],
                        "file_type": r[3],
                        "status": r[4],
                        "chunk_count": r[5] or 0,
                        "error_message": r[6],
                        "create_time": r[7].isoformat() if r[7] else None,
                        "indexed_at": r[8].isoformat() if r[8] else None,
                    })

                cursor.execute(stat_sql)
                ext_stats = {
                    r[0]: {
                        "total": r[1],
                        "pending": r[2],
                        "completed": r[3],
                        "failed": r[4],
                    }
                    for r in cursor.fetchall()
                }

        return {
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "items": items,
            "ext_stats": ext_stats,
        }

    def get_file_chunks(self, file_id: int) -> List[Dict[str, Any]]:
        """查询指定文件的全部切片明细（供前端预览）"""
        sql = """
            SELECT chunk_index, content, token_count, metadata, created_at
            FROM kb.kb_chunk
            WHERE file_id = %s
            ORDER BY chunk_index ASC;
        """
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (file_id,))
                rows = cursor.fetchall()
                return [
                    {
                        "chunk_index": r[0],
                        "content": r[1],
                        "token_count": r[2],
                        "metadata": r[3] if isinstance(r[3], dict) else json.loads(r[3] or "{}"),
                        "created_at": r[4].isoformat() if r[4] else None
                    }
                    for r in rows
                ]
