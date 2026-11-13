import os
import re
import sys
from pathlib import Path

import jieba
import psycopg2
from dotenv import load_dotenv, find_dotenv
from pgvector.psycopg2 import register_vector

# 确保项目根目录 knowledge 在 sys.path 中，方便直接运行脚本导入 app 模块
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.indexing.embedding_service import EmbeddingService

load_dotenv(find_dotenv())


def get_conn():
    conn = psycopg2.connect(
        host=os.getenv("PG_HOST"),
        port=int(os.getenv("PG_PORT")),
        dbname=os.getenv("PG_DB"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
    )
    # 注册 pgvector 扩展类型适配器
    register_vector(conn)
    return conn


def build_safe_or_tsquery(query: str) -> str:
    raw_words = jieba.cut_for_search(query)
    clean_tokens = []
    for w in raw_words:
        w = w.strip()
        if w and re.match(r"^[\u4e00-\u9fa5a-zA-Z0-9]+$", w):
            if w not in clean_tokens:
                clean_tokens.append(w)
    return " | ".join(clean_tokens)


def exp1_dense_vector_search(question: str, query_vec_str: str):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        print("\n" + "=" * 75)
        print("实验 1：pgvector 纯向量检索 (Dense Search) —— 距离 (<=>) vs 相似度 (1 - <=>)")
        print("=" * 75)
        sql = """
            SELECT
                c.id AS chunk_id,
                c.metadata ->> 'file_name' AS file_name,
                ROUND((c.embedding <=> %s::vector)::numeric, 4) AS cosine_distance,
                ROUND((1 - (c.embedding <=> %s::vector))::numeric, 4) AS cosine_similarity,
                ROW_NUMBER() OVER (ORDER BY c.embedding <=> %s::vector ASC) AS rank_d,
                LEFT(REPLACE(c.content, E'\n', ' '), 55) AS preview
            FROM kb.kb_chunk c
            JOIN kb.kb_file f ON c.file_id = f.id
            WHERE f.delete_flag = FALSE
            ORDER BY c.embedding <=> %s::vector ASC
            LIMIT 5;
        """
        cursor.execute(sql, (query_vec_str, query_vec_str, query_vec_str, query_vec_str))
        rows = cursor.fetchall()
        for r in rows:
            cid, fname, dist, sim, rank_d, preview = r
            print(
                f"[向量第 {rank_d} 名] ID:{cid:<4} | 余弦距离:{dist:<6} | 余弦相似度:{sim:<6} | 文件:{fname}\n"
                f"   摘要: {preview}..."
            )
    finally:
        cursor.close()
        conn.close()


def exp2_hybrid_rrf_search(question: str, query_vec_str: str, tsquery_str: str):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        print("\n" + "=" * 75)
        print("实验 2：终极 RRF 混合检索 (Dense Top-20 + Sparse Top-20 -> RRF Top-5)")
        print("=" * 75)
        recall_k = 20
        rrf_k = 60
        top_n = 5

        sql = """
            WITH dense_results AS (
                SELECT
                    c.id,
                    1 - (c.embedding <=> %s::vector) AS dense_score,
                    ROW_NUMBER() OVER (ORDER BY c.embedding <=> %s::vector ASC) AS rank_d
                FROM kb.kb_chunk c
                JOIN kb.kb_file f ON c.file_id = f.id
                WHERE f.delete_flag = FALSE
                ORDER BY c.embedding <=> %s::vector ASC
                LIMIT %s
            ),
            sparse_results AS (
                SELECT
                    c.id,
                    ts_rank_cd(c.tsv_content, to_tsquery('simple', %s)) AS sparse_score,
                    ROW_NUMBER() OVER (
                        ORDER BY ts_rank_cd(c.tsv_content, to_tsquery('simple', %s)) DESC
                    ) AS rank_s
                FROM kb.kb_chunk c
                JOIN kb.kb_file f ON c.file_id = f.id
                WHERE f.delete_flag = FALSE
                  AND c.tsv_content @@ to_tsquery('simple', %s)
                ORDER BY sparse_score DESC
                LIMIT %s
            ),
            rrf_fused AS (
                SELECT
                    COALESCE(d.id, s.id) AS chunk_id,
                    d.dense_score,
                    d.rank_d,
                    s.sparse_score,
                    s.rank_s,
                    (
                        COALESCE(1.0 / (%s + d.rank_d), 0.0) +
                        COALESCE(1.0 / (%s + s.rank_s), 0.0)
                    ) AS rrf_score
                FROM dense_results d
                FULL OUTER JOIN sparse_results s ON d.id = s.id
            )
            SELECT
                c.id AS chunk_id,
                c.metadata ->> 'file_name' AS file_name,
                r.rank_d,
                ROUND(COALESCE(r.dense_score, 0)::numeric, 4) AS dense_sim,
                r.rank_s,
                ROUND(COALESCE(r.sparse_score, 0)::numeric, 4) AS sparse_bm25,
                ROUND(r.rrf_score::numeric, 6) AS rrf_score,
                LEFT(REPLACE(c.content, E'\n', ' '), 55) AS preview
            FROM rrf_fused r
            JOIN kb.kb_chunk c ON r.chunk_id = c.id
            ORDER BY r.rrf_score DESC
            LIMIT %s;
        """
        params = (
            # dense_results 参数 (4个: SELECT距离, ROW_NUMBER排序, ORDER BY排序, LIMIT)
            query_vec_str, query_vec_str, query_vec_str, recall_k,
            # sparse_results 参数 (4个: SELECT打分, ROW_NUMBER排序, WHERE匹配, LIMIT)
            tsquery_str, tsquery_str, tsquery_str, recall_k,
            # rrf_fused 参数 (2个: 向量侧rrf_k, 全文侧rrf_k)
            rrf_k, rrf_k,
            # 最终 LIMIT 参数 (1个)
            top_n,
        )
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        print(f"{'最终排名':<6} | {'切片ID':<6} | {'向量名次(得分)':<16} | {'全文名次(得分)':<16} | {'RRF总分':<10} | {'来源文件'}")
        print("-" * 95)
        for idx, r in enumerate(rows, start=1):
            cid, fname, rank_d, d_sim, rank_s, s_bm25, rrf_score, preview = r
            d_info = f"#{rank_d} ({d_sim})" if rank_d else "未命中"
            s_info = f"#{rank_s} ({s_bm25})" if rank_s else "未命中"
            print(f"Top-{idx:<4} | {cid:<8} | {d_info:<18} | {s_info:<18} | {rrf_score:<10} | {fname}")
    finally:
        cursor.close()
        conn.close()


def exp3_explain_analyze(query_vec_str: str, tsquery_str: str):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        print("\n" + "=" * 75)
        print("实验 3：使用 EXPLAIN ANALYZE 查看 PostgreSQL 真实执行计划与耗时")
        print("=" * 75)
        explain_sql = """
            EXPLAIN ANALYZE
            SELECT c.id
            FROM kb.kb_chunk c
            WHERE c.tsv_content @@ to_tsquery('simple', %s)
            ORDER BY c.embedding <=> %s::vector ASC
            LIMIT 5;
        """
        cursor.execute(explain_sql, (tsquery_str, query_vec_str))
        plan_lines = cursor.fetchall()
        for line in plan_lines:
            print("  ", line[0])
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    embedder = EmbeddingService()
    test_question = "请问外国人来华商务邀请函怎么办理？"
    print(f"正在调用 Embedding 模型将问题向量化: '{test_question}' ...")
    vec_list = embedder.embedding_query(test_question)
    vec_str = str(vec_list)
    ts_query = build_safe_or_tsquery(test_question)

    exp1_dense_vector_search(test_question, vec_str)
    exp2_hybrid_rrf_search(test_question, vec_str, ts_query)
    exp3_explain_analyze(vec_str, ts_query)
