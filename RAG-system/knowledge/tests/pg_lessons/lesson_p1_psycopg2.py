import os

import psycopg2
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
# print("=== 实验 1: fetchone() 与 fetchall() 的返回结构 ===")

# print("\n=== 实验 2: 验证未 commit 的修改通过 rollback 撤销 ===")


# 故意把状态改成 'TEST_TEMP_STATUS'，但不 commit


# 执行回滚


# print("\n=== 实验 3: 体验 PostgreSQL 事务报错锁死与 rollback 解锁 ===")

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
    # print("=== 实验 1: fetchone() 与 fetchall() 的返回结构 ===")
    sql1 = """
        select * from kb.kb_file where delete_flag= %s
    """
    cursor.execute(sql1,[False])
    one_row = cursor.fetchone()
    # one_row:(224584880095233, '金柚GEO全球交付协同SOP-V1.1.pdf', 'https://geo-test-1327559436.cos.ap-guangzhou.myqcloud.com/temp/20260903/8f0ce679-eb37-4d27-993e-38c04b5afd68/%E9%87%91%E6%9F%9AGEO%E5%85%A8%E7%90%83%E4%BA%A4%E4%BB%98%E5%8D%8F%E5%90%8CSOP-V1.1.pdf', 'pdf', 'PDF', '', 16729952616449, datetime.datetime(2026, 9, 3, 21, 20, 16, 440000), 16729952616449, datetime.datetime(2026, 9, 3, 21, 20, 16, 440000), False, 'PENDING', 23, None, datetime.datetime(2026, 11, 7, 21, 49, 29, 866274))
    print(f"one_row:{one_row}")

    all_rows = cursor.fetchall()
    print(f"all_rows:{len(all_rows)}")

    # print("\n=== 实验 2: 验证未 commit 的修改通过 rollback 撤销 ===")
    target_id = all_rows[0][0]
    original_status = all_rows[0][2]
    print(f"目标文件 ID: {target_id}, 原始状态: {original_status}")
    sql2 = """
        update kb.kb_file set status = %s where id = %s
    """
    cursor.execute(sql2,["TEST_TEMP_STATUS",1])
    cursor.execute("SELECT status FROM kb.kb_file WHERE id = %s;", [target_id])
    print(f"当前事务内查到的状态: {cursor.fetchone()[0]}")

    conn.rollback()

    print("\n=== 实验 3: 体验 PostgreSQL 事务报错锁死与 rollback 解锁 ===")
    # try:
    #     cursor.execute("select unknow_column from kb.kb_file")
    # except Exception as e:
    #     print(f"捕获到 SQL 错误: {e.pgerror.strip() if hasattr(e, 'pgerror') and e.pgerror else e}")
    #     # 此时如果不 rollback，直接执行正常 SQL 会报错：
    # try:
    #     cursor.execute("SELECT 1;")
    # except Exception as e:
    #     print(f"未 rollback 直接发新 SQL 的后果: {e}")
    #   # 调用 rollback 解锁事务后，连接恢复正常：
    # conn.rollback()
    # cursor.execute("SELECT 1;")
    # print(f"调用 conn.rollback() 解锁后，执行 SELECT 1 成功返回: {cursor.fetchone()[0]}")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    run_lesson_p1()

