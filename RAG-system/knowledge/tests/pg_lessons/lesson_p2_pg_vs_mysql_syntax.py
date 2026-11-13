import os

import psycopg2
from dotenv import load_dotenv, find_dotenv
from psycopg2._psycopg import cursor

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
    print("实验 1：三层命名空间 (Database -> Schema -> Table) 与 search_path")
    try:

        sql1 = """
            select current_database(),current_schema(),
            current_setting('search_path');
        """
        cursor.execute(sql1)
        res = cursor.fetchone()
        print(res) #('knowledge', 'public', '"$user", public')
        # 查询当前库下所有的自定义 Schema 及其包含的表数量
        sql2 = """
            select table_schema,count(table_name)
            from information_schema.tables
            where table_schema not in ('pg_catalog','information_schema')
            group by table_schema;
        """
        cursor.execute(sql2)
        res2 = cursor.fetchall()
        print(res2) #[('kb', 2)]
    finally:
        cursor.close()
        conn.close()

def exp2_type_cast_and_jsonb():
    conn = get_conn()
    cursor = conn.cursor()
    try:
        # 1. 演示 :: 强类型转换与 pg_typeof() 查看底层类型
        cursor.execute(
            """
            select 
            '1024'::int +1 as int_calc,
            pg_typeof('1024'::int) as type_int,
            pg_typeof('[0.1,0.2,0.3]'::vector) as type_vec;
            """
        )
        res = cursor.fetchall()
        print(res) # [(1025, 'integer', 'vector')]

        # 2. 从 kb.kb_chunk 真实读取一条数据，对比 JSONB 的 -> 与 ->> 算子
        cursor.execute("""
            select
                metadata-> 'file_name' as jsonb_obj,
                pg_typeof(metadata->'file_name') as type_arrow,
                metadata->>'file_name' as text_val,
                pg_typeof(metadata->>'file_name') as type_double_arrow
            from kb.kb_chunk
            limit 1;
        """)
        chunk_row = cursor.fetchone()
        if chunk_row:
            print(f"[真实切片演示] -> 返回: {chunk_row[0]} (类型: {chunk_row[1]})")
            print(f"[真实切片演示] ->> 返回: {chunk_row[2]} (类型: {chunk_row[3]})")
        else:
            cursor.execute("""                                                                                          
                            SELECT
                                '{"file_name": "差旅制度.pdf", "ext": "pdf"}'::jsonb -> 'file_name',                             
                                '{"file_name": "差旅制度.pdf", "ext": "pdf"}'::jsonb ->> 'file_name';                            
            		""")
            demo_row = cursor.fetchone()
            print(f"[字面量演示] -> 返回: {demo_row[0]} | ->> 返回: {demo_row[1]}")



    finally:
        cursor.close()
        conn.close()

def exp3_filter_aggregation():
    print("实验 3：COUNT(*) FILTER (WHERE ...) 单次扫描条件聚合")
    conn = get_conn()
    cursor = conn.cursor()
    try:
        sql="""
            select
                COUNT(*) AS total_active,
                    COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed,
                    COUNT(*) FILTER (WHERE status = 'PENDING') AS pending,
                    COUNT(*) FILTER (WHERE status = 'FAILED') AS failed,
                    COUNT(*) FILTER (WHERE file_ext = 'pdf') AS pdf_count,
                    COUNT(*) FILTER (WHERE file_ext IN ('doc', 'docx')) AS word_count,
                    COALESCE(SUM(chunk_count), 0) AS total_chunks
            from kb.kb_file
        """
        cursor.execute(sql)
        res = cursor.fetchone()
        print(
            f"有效总数: {res[0]} | COMPLETED: {res[1]} | PENDING: {res[2]} | FAILED: {res[3]}\n"
            f"PDF文件数: {res[4]} | Word文件数: {res[5]} | 累计切片数: {res[6]}"
        )
    finally:
        cursor.close()
        conn.close()
def exp4_for_update_skip_locked():
    print("实验 4：双连接并发模拟 FOR UPDATE SKIP LOCKED 非阻塞抢单")
    conn_worker_a = get_conn()
    conn_worker_b = get_conn()
    cur_a = conn_worker_a.cursor()
    cur_b = conn_worker_b.cursor()
    sql = """
          SELECT id, name, status
          FROM kb.kb_file
          WHERE delete_flag = FALSE
          ORDER BY id ASC LIMIT 2
                FOR \
          UPDATE SKIP LOCKED; \
          """
    try:
        # 1. Worker A 先执行查询，锁住前 2 条记录（注意：此时不调用 conn_worker_a.commit()，保持行锁持有状态）
        cur_a.execute(sql)
        rows_a = cur_a.fetchall()
        print("[Worker A] 锁定并拉取到的前 2 条文件（事务未提交，行锁持有中）:")
        for r in rows_a:
            print(f"   -> ID: {r[0]} | Name: {r[1]} | Status: {r[2]}")

        # 2. Worker B 紧接着执行完全相同的 SQL（LIMIT 2）
        # 因为有 SKIP LOCKED，Worker B 不会卡住等待 Worker A，而是直接跳过被 A 锁住的 2 行，拿到第 3、4 行！
        cur_b.execute(sql)
        rows_b = cur_b.fetchall()
        print("[Worker B] 同时执行相同 SQL，自动跳过被锁行，零阻塞拿到的 2 条文件:")
        for r in rows_b:
            print(f"   -> ID: {r[0]} | Name: {r[1]} | Status: {r[2]}")

    finally:
        # 实验结束，回滚两个事务以释放排他锁，不修改数据库任何状态
        conn_worker_a.rollback()
        conn_worker_b.rollback()
        cur_a.close()
        cur_b.close()
        conn_worker_a.close()
        conn_worker_b.close()
        print("两个 Worker 事务已回滚，行锁已安全释放。")

if __name__ == "__main__":
    # run_lesson_p1()
    # exp2_type_cast_and_jsonb()
    # exp3_filter_aggregation()
    exp4_for_update_skip_locked()
