import sys
import time
from pathlib import Path
from typing import List, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.retrieval.hybrid_retriever import HybridRetriever

# 基于当前已入库真实制度构建的黄金评测集 (Ground Truth Benchmark)
BENCHMARK_CASES: List[Dict[str, str]] = [
    {
        "id": "Q1",
        "category": "同义语义泛化",
        # 注意：故意不用原文的“外国人”、“来华”、“商务邀请函”，改用同义词测试向量能力
        "question": "外籍客户来中国洽谈业务，怎么申请办理官方邀请信？",
        "expected_file": "外国人来华商务邀请函办理流程.docx",
    },
    {
        "id": "Q2",
        "category": "中英专有名词",
        "question": "香港Payroll项目的薪资核算SOP操作流程是什么？",
        "expected_file": "香港Payroll项目-SOP.xlsx",
    },
    {
        "id": "Q3",
        "category": "英文缩写检索",
        "question": "去意大利办理ICT内部调动签证需要什么材料？",
        "expected_file": "意大利ICT.docx",
    },
    {
        "id": "Q4",
        "category": "国别签证流程",
        "question": "德国项目签证的申请材料与办理要求有哪些？",
        "expected_file": "0103 德国项目签证.pdf",
    },
    {
        "id": "Q5",
        "category": "国别签证流程",
        "question": "员工去越南出差办签证的SOP办理流程",
        "expected_file": "越南办理流程 sop.pdf",
    },
    {
        "id": "Q6",
        "category": "专业签证类型",
        "question": "俄罗斯设备安装调试签证需要准备什么手续？",
        "expected_file": "俄罗斯设备签证.docx",
    },
    {
        "id": "Q7",
        "category": "模板文书查找",
        "question": "申请签证用的英文版在职证明模板怎么写？",
        "expected_file": "英文_在职证明模板.doc",
    },
    {
        "id": "Q8",
        "category": "领区表单检索",
        "question": "波兰签证北京上海领区的申请表怎么填？",
        "expected_file": "波兰国别签证表-北京上海领区-Country-Visa-Application-Form-Beijing-Consular-District.docx",
    },
]


def evaluate_mode(
        retriever: HybridRetriever,
        mode: str,
        top_k: int = 5,
) -> Dict[str, Any]:
    hits = 0
    rr_sum = 0.0
    total_ms = 0.0
    case_details = []

    for case in BENCHMARK_CASES:
        t0 = time.perf_counter()
        # 评测时关闭缓存 (use_cache=False)，测量数据库真实检索表现
        chunks = retriever.retrieve(
            query=case["question"],
            top_k=top_k,
            mode=mode,
            use_cache=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        total_ms += elapsed_ms

        # 查找目标文件首次出现的排名 (1-based)
        hit_rank = None
        for idx, c in enumerate(chunks, start=1):
            if case["expected_file"] in c.file_name or c.file_name in case["expected_file"]:
                hit_rank = idx
                break

        if hit_rank is not None:
            hits += 1
            reciprocal_rank = 1.0 / hit_rank
        else:
            reciprocal_rank = 0.0

        rr_sum += reciprocal_rank
        case_details.append({
            "id": case["id"],
            "category": case["category"],
            "hit_rank": hit_rank,
            "rr": round(reciprocal_rank, 4),
            "top1_file": chunks[0].file_name if chunks else "无召回",
        })

    n = len(BENCHMARK_CASES)
    return {
        "mode": mode,
        "hit_rate": round(hits / n, 4),
        "mrr": round(rr_sum / n, 4),
        "avg_ms": round(total_ms / n, 2),
        "details": case_details,
    }


def run_benchmark():
    retriever = HybridRetriever(rrf_k=60, recall_k=20)
    top_k = 5
    modes = ["dense", "sparse", "hybrid"]
    summary_results = []

    print("\n" + "=" * 90)
    print(f"🚀 开始执行企业知识库检索基准评测 (共 {len(BENCHMARK_CASES)} 题, Top-{top_k}, 禁用缓存实测)")
    print("=" * 90)

    for mode in modes:
        res = evaluate_mode(retriever, mode=mode, top_k=top_k)
        summary_results.append(res)

        print(f"\n--- 模式 [{mode.upper()}] 逐题命中明细 ---")
        for d in res["details"]:
            rank_str = f"第 {d['hit_rank']} 名 (RR={d['rr']})" if d["hit_rank"] else "❌ 未命中"
            print(f"  {d['id']} [{d['category']}] -> 命中名次: {rank_str:<18} | Top-1 文件: {d['top1_file'][:40]}")

    print("\n" + "=" * 90)
    print("📊 三种检索模式最终量化对比汇总表 (Final Evaluation Matrix)")
    print("=" * 90)
    print(f"{'检索模式 (Mode)':<18} | {'HitRate@5 (召回命中率)':<24} | {'MRR@5 (平均倒数排名)':<24} | {'平均检索耗时 (ms)':<18}")
    print("-" * 90)
    for r in summary_results:
        hit_pct = f"{r['hit_rate'] * 100:.1f}%"
        print(f"{r['mode'].upper():<18} | {hit_pct:<24} | {r['mrr']:<24.4f} | {r['avg_ms']:<18.2f}")
    print("=" * 90)

if __name__ == "__main__":
        run_benchmark()