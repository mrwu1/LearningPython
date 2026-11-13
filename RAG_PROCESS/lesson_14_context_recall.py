from typing import List

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from utils.model import get_llm


class GroundTruthStatementCoverage(BaseModel):
    ground_truth_statement: str = Field(
        ..., description="从标准参考答案中拆解出的单个核心事实点"
    )
    is_covered: bool = Field(
        ..., description="该事实点是否已经在检索出的参考上下文中被包含覆盖"
    )
    reason: str = Field(..., description="核验理由")


class ContextRecallAuditReport(BaseModel):
    coverages: List[GroundTruthStatementCoverage] = Field(
        ..., description="标准答案事实点在上下文中的覆盖核验列表"
    )
# ================== 4. 检索召回率计算函数 ==================
def calculate_context_recall(context:str,ground_truth:str)->float:
    """计算检索上下文召回率：上下文覆盖的标准事实数 / 标准事实总数"""
    llm = get_llm()
    grader = llm.with_structured_output(
        schema=ContextRecallAuditReport, method="function_calling"
    )
    system_prompt = (
        "你是一位检索召回率评估专家。\n"
        "任务步骤：\n"
        "1. 把专家提供的【标准参考答案】拆解为若干个不可或缺的关键事实点；\n"
        "2. 检查【检索出来的上下文】是否已经把这些事实点全部包含进来了 (is_covered)；\n"
        "如果上下文漏掉了某个关键事实，坚决标为 is_covered=False！"
    )
    user_prompt = f"【检索出来的上下文】：\n{context}\n\n【标准参考答案】：\n{ground_truth}"
    report: ContextRecallAuditReport = grader.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )

    if not report.coverages:
        return 0.0

    covered_count = sum(1 for c in report.coverages if c.is_covered)
    total_count = len(report.coverages)
    score = covered_count / total_count
    print(
        f"\n🎯 [Context Recall 细分审计]: 标准答案含 {total_count} 个核心事实，检索命中 {covered_count} 个"
    )
    for c in report.coverages:
        icon = "✅" if c.is_covered else "❌ (严重漏召回)"
        print(f"   {icon} 标准事实: 【{c.ground_truth_statement}】")
        print(f"      审计理由: {c.reason}")

    return round(score, 4)
if __name__ == "__main__":
    print("🧪 实验 C：校准【完美无缺的上下文 (预期 100% 召回)】")
    # 财务专家认定的标准答案（包含两个硬性制度要点）
    ground_truth = (
        "总监在深圳出差每晚住宿限额650元。未经特批私自升舱产生的超额费用不予报销。"
    )

    # 模拟检索器很给力，把这两个条款全搜全了
    context_full = (
        "【集团差旅制度】超一线城市总监级别住宿上限为650元/晚。"
        "未经特批私自升舱产生的超额费用一律不予报销。"
    )
    score_c = calculate_context_recall(
        context=context_full, ground_truth=ground_truth
    )
    print(f"📊 实验 C 召回率得分: {score_c * 100:.1f}%\n")

    print("🧪 实验 D：校准【存在漏检缺陷的上下文 (预期 50% 召回)】")
    # 模拟检索器出现切片或语义漏搜：只搜到了住宿标准，但把“私自升舱”条款漏掉了！
    context_incomplete = (
        "【集团差旅制度】超一线城市总监级别住宿上限为650元/晚。"  # 缺失升舱条款！
    )
    score_d = calculate_context_recall(
        context=context_incomplete, ground_truth=ground_truth
    )
    print(f"📊 实验 D 召回率得分: {score_d * 100:.1f}%\n")