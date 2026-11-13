"""lesson_16_ragas_composite.py

    RAG 黄金三元组量化评估聚合器
    职责：
    1. 导入三个独立的原子指标计算函数；
    2. 接收标准四元组样本进行统一批处理；
    3. 输出量化评估报表与均值统计。
"""
from typing import Dict, List, Any

from lesson_13_ragas_evaluation import calculate_faithfulness
from lesson_14_context_recall import calculate_context_recall
from lesson_15_answer_relevance import calculate_answer_relevance


def evaluate_single_sample(sample: Dict[str, str]) -> Dict[str, float]:
    """对单条样本执行三维度评估并计算综合得分"""
    q = sample["question"]
    gt = sample["ground_truth"]
    c = sample["context"]
    a = sample["answer"]

    # 分别调用三个独立模块
    faithfulness = calculate_faithfulness(context=c, answer=a)
    context_recall = calculate_context_recall(context=c, ground_truth=gt)
    answer_relevance = calculate_answer_relevance(question=q, answer=a)

    composite_score = round(
        (faithfulness + context_recall + answer_relevance) / 3.0, 4
    )

    return {
        "faithfulness": faithfulness,
        "context_recall": context_recall,
        "answer_relevance": answer_relevance,
        "composite_score": composite_score,
    }

def evaluate_batch(dataset: List[Dict[str, str]]) -> Dict[str, Any]:
        """对批量样本执行评测并计算数据集全局平均指标"""
        detailed_results = []
        total_faith = 0.0
        total_recall = 0.0
        total_relevance = 0.0
        n = len(dataset)

        if n == 0:
            return {"error": "Dataset is empty"}

        for idx, item in enumerate(dataset, 1):
            print(f"\n--- 正在评估样本 [{idx}/{n}]: {item.get('name', '未命名')} ---")
            metrics = evaluate_single_sample(item)
            detailed_results.append({"name": item.get("name"), "metrics": metrics})

            total_faith += metrics["faithfulness"]
            total_recall += metrics["context_recall"]
            total_relevance += metrics["answer_relevance"]

        summary = {
            "sample_count": n,
            "avg_faithfulness": round(total_faith / n, 4),
            "avg_context_recall": round(total_recall / n, 4),
            "avg_answer_relevance": round(total_relevance / n, 4),
            "avg_composite_score": round(
                (total_faith + total_recall + total_relevance) / (3.0 * n), 4
            ),
        }

        return {"summary": summary, "details": detailed_results}

if __name__ == "__main__":
        # 评测数据集 (包含两个对照样本)
    test_cases = [
            {
                "name": "基准合格样本 (全部满足)",
                "question": "总监去深圳出差，每晚酒店报销上限是多少？私自升舱能报吗？",
                "ground_truth": "总监深圳出差住宿上限为650元/晚。未经特批私自升舱产生的超额费用一律不予报销。",
                "context": (
                    "【集团差旅制度】超一线城市（北上广深）总监级别住宿上限为650元/晚。"                                 
                    "未经特批私自升舱产生的超额费用一律不予报销。"
                ),
                "answer":
                "根据集团制度，总监在深圳出差每晚住宿上限为650元。未经特批私自升舱产生的超额费用公司不予报销。",
            },
            {
                "name": "缺陷样本 (存在漏检与回避回答)",
                "question": "总监去深圳出差，每晚酒店报销上限是多少？私自升舱能报吗？",
                "ground_truth": "总监深圳出差住宿上限为650元/晚。未经特批私自升舱产生的超额费用一律不予报销。",
                "context": (
                    "【集团差旅制度】超一线城市初级员工住宿上限为450元/晚。"  # 检索漏掉总监条款
                ),
                "answer": (
                    "深圳是一座现代化都市，大家出差要注意人身财产安全，发票请按规定平整粘贴。"  # 答非所问
                ),
            },
    ]
    report = evaluate_batch(test_cases)
    print("📋 批量评测汇总大盘 (Scoreboard Summary)")
    print("=" * 60)
    s = report["summary"]
    print(f"评估样本总数: {s['sample_count']}")
    print(f"平均忠实度 (Faithfulness)   : {s['avg_faithfulness'] * 100:.2f}%")
    print(f"平均召回率 (Context Recall) : {s['avg_context_recall'] * 100:.2f}%")
    print(f"平均相关度 (Answer Relevance): {s['avg_answer_relevance'] * 100:.2f}%")
    print(f"全局综合得分 (Composite)    : {s['avg_composite_score'] * 100:.2f}%")