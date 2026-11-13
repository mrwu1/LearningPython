import os

import psycopg2
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


def get_conn():
    return psycopg2.connect(
        host=os.getenv("PG_HOST"),
        port=int(os.getenv("PG_PORT")),
        dbname=os.getenv("PG_DB"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
    )

def run_lesson_p1():
    conn = get_conn()
    cursor = conn.cursor()
     # • 实验 1：在 kb.kb_file 上演练窗口函数 ROW_NUMBER() OVER (...) 的全局排名与分组（PARTITION BY）排名。
    # 需求：按文件格式 (file_ext) 分组，在每种格式内部按切片数 (chunk_count) 从高到低排名，
    # 并结合 WITH (CTE) 取出每种格式下切片数最多的前 2 名文件
    try:
        sql = """ \
              with ranked_files as (select id, \
                                           name, \
                                           file_ext, \
                                           chunk_count, \
                                           row_number() over(partition by file_ext order by chunk_count desc,id asc) as ext_rank, row_number() over(order by chunk_count desc,id asc) as group_count \
                                    FROM kb.kb_file \
                                    WHERE delete_flag = FALSE \
                                      AND status = 'COMPLETED' \
                                      AND chunk_count > 0) \
              select id, name, file_ext, chunk_count, ext_rank, group_count \
              from ranked_files \
              WHERE ext_rank <= 2 \
              ORDER BY file_ext ASC, ext_rank ASC; \
             """
        cursor.execute(sql)
        rows = cursor.fetchall()
        if not rows:
            print("当前尚无 COMPLETED 且 chunk_count > 0 的文件，请先通过控制台入库几个文件。")
        for r in rows:
            print(f"[{r[0]:<4}] 格式内第 {r[1]} 名 (全局第 {r[2]:<2} 名) | 切片数: {r[3]:<3} | 文件: {r[4]}")
    finally:
        cursor.close()
        conn.close()

def run_lesson_p2():
    print("实验 3：RRF 混合检索外层骨架演练 (WITH + FULL OUTER JOIN + COALESCE)")
    try:
        conn = get_conn()
        cursor = conn.cursor()
        # 使用内存虚拟数据 (VALUES) 构造最纯粹的两路召回结果，也可用真实 kb_chunk 表测试：
        # 假设路 A (模拟向量检索) 召回了切片 ID: 101(第1名), 102(第2名), 104(第3名)
        # 假设路 B (模拟全文检索) 召回了切片 ID: 102(第1名), 103(第2名), 104(第3名)

        sql = """
            WITH mock_dense AS (
                SELECT
    			    v.chunk_id,
    			    v.sim_score,
    			    ROW_NUMBER() OVER (ORDER BY v.sim_score DESC) AS rank_d
                FROM (
    			    VALUES
                            (101, 0.88),
                            (102, 0.82),
                            (104, 0.75)
                    ) AS v(chunk_id, sim_score)
            ),
            mock_sparse AS (
                SELECT
    			    s.chunk_id,
    			    s.bm25_score,
    			    ROW_NUMBER() OVER (ORDER BY s.bm25_score DESC) AS rank_s
                FROM (
    			    VALUES
                            (102, 3.40),
                            (103, 2.10),
                            (104, 1.05)
                    ) AS s(chunk_id, bm25_score)
                )
            select coalesce(d.chunk_id,s.chunk_id) as final_chunk_id,
                d.rank_d,
                s.rank_s,
                round(coalesce(1.0/(60+d.rank_d),0.0),6) as dense_rrf
                round(coalesce(1.0/(60+s.rank_s),0.0),6))) AS sparse_rrf,
                round(
                    coalesce(1.0/(60+d.rank_d),0.0)+
                    coalesce(1.0/(60+s.rank_s),0.0)
                )as total_rrf_score
            from mock_dense d 
            full outer join mock_sparse s on s.chunk_id = d.chunk_id
            order by total_rrf_score desc
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        print(f"{'切片ID':<8} | {'向量名次':<8} | {'全文名次':<8} | {'向量RRF得分':<12} | {'全文RRF得分':<12} | {'总RRF得分': < 12}")
        print("-" * 78)
        for r in rows:
            chunk_id, rank_d, rank_s, d_rrf, s_rrf, total_rrf = r
        print(
            f"{chunk_id:<10} | "
            f"{str(rank_d):<10} | "
            f"{str(rank_s):<10} | "
            f"{d_rrf:<14} | "
            f"{s_rrf:<14} | "
            f"{total_rrf:<12}"
        )
    finally:
        cursor.close()
        conn.close()
if __name__ == "__main__":
    # run_lesson_p1()
    run_lesson_p2()

