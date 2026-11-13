import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.retrieval.hybrid_retriever import HybridRetriever
from loguru import logger


def run_pool_benchmark_and_safety_test():
    print("=" * 80)
    print("🚀 开始验证 Module 2.1 改造点 1：连接池化性能与异常事务清洗防御")
    print("=" * 80)

    retriever = HybridRetriever()

    # -------------------------------------------------------------------------
    # 测试项 1：性能测试 —— 对比第 1 次（冷启动连接+注册OID）与后续 10 次（池化热复用）的耗时
    # -------------------------------------------------------------------------
    test_query = "意大利ICT签证办理"

    # 先获取一次 embedding 向量，排除网络调用 Embedding API 的公网干扰，只测纯数据库层耗时
    print("\n[步骤 1] 预计算向量（排除公网 Embedding API 耗时干扰）...")
    vec = retriever.embedder.embedding_query(test_query)
    vec_str = str(vec)

    # 第一次冷查询（从池中取出物理连接 + register_vector）
    t_cold_start = time.perf_counter()
    res_cold = retriever.search_dense(query=test_query, top_k=3, query_vec_str=vec_str)
    cold_ms = (time.perf_counter() - t_cold_start) * 1000
    print(f"👉 第 1 次检索耗时 (冷连接建立): {cold_ms:.2f} ms | 召回: {len(res_cold)} 条")

    # 连续执行 10 次池化热复用检索
    warm_times = []
    for i in range(10):
        t_start = time.perf_counter()
        res_warm = retriever.search_dense(query=test_query, top_k=3, query_vec_str=vec_str)
        elapsed_ms = (time.perf_counter() - t_start) * 1000
        warm_times.append(elapsed_ms)

    avg_warm_ms = sum(warm_times) / len(warm_times)
    min_warm_ms = min(warm_times)
    max_warm_ms = max(warm_times)
    print(f"👉 后续 10 次热连接检索: 平均 {avg_warm_ms:.2f} ms (最低: {min_warm_ms:.2f} ms, 最高: {max_warm_ms:.2f} ms)")
    
    assert avg_warm_ms < 100.0, f"性能未达标：热连接平均耗时 {avg_warm_ms:.2f}ms 超过 100ms 阈值！"
    print("✅ 测试项 1 通过：连接池复用使得纯 DB 检索耗时成功稳定在毫秒级！")

    # -------------------------------------------------------------------------
    # 测试项 2：安全性测试 —— 验证异常发生时的自动 rollback 与连接清洗防御
    # -------------------------------------------------------------------------
    print("\n[步骤 2] 模拟故障注入：执行错误 SQL，验证连接池防污染机制...")
    
    # 故意借出一个连接并执行会导致 PostgreSQL 报错的非法 SQL
    error_occurred = False
    try:
        with retriever._get_connection() as bad_conn:
            with bad_conn.cursor() as cur:
                cur.execute("SELECT * FROM kb.non_existent_table_for_test;")
    except Exception as e:
        error_occurred = True
        print(f"   [预期捕获到异常]: {e}")

    assert error_occurred, "测试设计异常：非法 SQL 未抛出预期错误！"

    # 关键验证：借出刚刚被异常污染归还的连接，再次执行正常查询。
    # 如果防御未生效，此处会抛出：current transaction is aborted, commands ignored until end of transaction block
    try:
        res_after_error = retriever.search_dense(query=test_query, top_k=1, query_vec_str=vec_str)
        assert len(res_after_error) > 0, "查询结果为空！"
        print("✅ 测试项 2 通过：异常发生后，连接被严格 rollback 清洗，后续借出依然健康运行，未发生脏连接污染！")
    except Exception as e:
        print(f"❌ 测试项 2 失败：连接池遭到了脏事务污染！错误信息: {e}")
        raise e

    print("\n" + "=" * 80)
    print("🏆 改造点 1 全部验证通过！连接池具备生产级性能与异常自愈防御能力。")
    print("=" * 80)


if __name__ == "__main__":
    run_pool_benchmark_and_safety_test()
