import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.retrieval.hybrid_retriever import HybridRetriever


def test_two_stage_rerank():
    print("=" * 85)
    print("🚀 开始验证 Module 2.2：两阶段检索 (加权RRF粗排 + 智谱 Cross-Encoder 重排)")
    print("=" * 85)

    retriever = HybridRetriever()

    # 重点测试阶段一失利的两个典型案例：Q5 (越南办理流程) 与 Q7 (英文在职证明)
    test_cases = [
        {
            "id": "Q5",
            "query": "员工去越南出差办签证的SOP办理流程",
            "expected_file": "越南办理流程 sop.pdf"
        },
        {
            "id": "Q7",
            "query": "申请签证用的英文版在职证明模板怎么写？",
            "expected_file": "英文_在职证明模板.doc"
        }
    ]

    for tc in test_cases:
        qid = tc["id"]
        q = tc["query"]
        target = tc["expected_file"]

        print(f"\n【测试题 {qid}】Query: '{q}'")
        print(f"🎯 预期目标文件: {target}")
        print("-" * 85)

        # 1. 对照组：关闭重排（纯粗排 RRF）
        t0 = time.perf_counter()
        coarse_results = retriever.retrieve(query=q, top_k=5, mode="hybrid", use_cache=False, use_rerank=False)
        t_coarse_ms = (time.perf_counter() - t0) * 1000

        print(f"📊 [对照组：纯粗排 RRF] (耗时 {t_coarse_ms:.1f}ms):")
        coarse_rank = None
        for rank, c in enumerate(coarse_results, start=1):
            is_hit = "🎯 HIT!" if target in c.file_name else ""
            if target in c.file_name and coarse_rank is None:
                coarse_rank = rank
            print(f"   #{rank} | RRF分: {c.score:.6f} | 文件: {c.file_name} {is_hit}")

            # 2. 实验组：开启 Cross-Encoder 精排重排
        t1 = time.perf_counter()
        rerank_results = retriever.retrieve(query=q, top_k=5, mode="hybrid", use_cache=False, use_rerank=True)
        t_rerank_ms = (time.perf_counter() - t1) * 1000

        print(f"\n🏆 [实验组：粗排 + Cross-Encoder 重排] (耗时 {t_rerank_ms:.1f}ms):")
        rerank_rank = None
        for rank, c in enumerate(rerank_results, start=1):
            is_hit = "🎯 HIT!" if target in c.file_name else ""
            if target in c.file_name and rerank_rank is None:
                rerank_rank = rank
            print(f"   #{rank} | 重排分: {c.score:.6f} (Rerank={c.rerank_score}) | 文件: {c.file_name} {is_hit}")

            # 输出跃迁对比
        coarse_str = f"第 {coarse_rank} 名" if coarse_rank else "❌ 未进前5"
        rerank_str = f"第 {rerank_rank} 名" if rerank_rank else "❌ 未进前5"
        print(f"\n📈 排名跃迁: 纯粗排 [{coarse_str}]  ==>  Cross-Encoder 重排后 [{rerank_str}]")

    print("\n" + "=" * 85)
    print("🏁 测试执行完毕！")
    print("=" * 85)


if __name__ == "__main__":
    test_two_stage_rerank()