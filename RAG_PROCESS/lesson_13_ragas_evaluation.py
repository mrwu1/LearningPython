from typing import List

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from utils.model import get_llm


# ================== 1. 忠实度审计契约 ==================

class StatementVerification(BaseModel):
    statement: str = Field(
        ...,
        description="该事实是否能在参考文档中找到直接依据：True 或 False"
    )
    is_supported: bool = Field(
        ..., description="该事实是否能在参考文档中找到直接依据：True 或 False"
    )
    reason: str = Field(..., description="核验判断理由")

class FaithfulnessAuditReport(BaseModel):
    verifications: List[StatementVerification] = Field(
        ...,
        description="拆解出的所有事实命题核验列表"
    )
# ================== 2. 忠实度计算函数 ==================

def calculate_faithfulness(context:str,answer:str):
    """计算忠实度得分：支持的命题数 / 总命题数"""
    llm = get_llm()
    grader = llm.with_structured_output(
        schema = FaithfulnessAuditReport,
        method="function_calling"
    )
    system_prompt = (
        "你是一位冷酷严苛的法务审计员，正在给一份AI回答进行事实真实性审查。\n"
        "任务步骤：\n"
        "1. 把【待审计回答】拆解为若干个不可分割的原子事实（比如包含地点、数字、权限的单个陈述句）；\n"
        "2. 逐一比对【参考文档】，只要文档里没有提及，坚决标为 is_supported=False！"
    )
    user_prompt = f"【参考文档】：\n{context}\n\n【待审计回答】：\n{answer}"
    report:FaithfulnessAuditReport = grader.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )
    if not report.verifications:
        return 0.0
    supported_count = sum(1 for v in report.verifications if v.is_supported)
    total_count = len(report.verifications)
    score = supported_count / total_count
    print(
        f"\n🔬 [事实核验明细]: 共拆解出 {total_count} 条事实，有据可查 {supported_count} 条"
    )
    for v in report.verifications:
        icon = "✅" if v.is_supported else "❌ (严重幻觉)"
        print(f"   {icon} 事实: 【{v.statement}】")
        print(f"      审计理由: {v.reason}")

    return round(score, 4)


if __name__ == "__main__":
    # 真实企业背景规章
    standard_doc = (
        "【集团差旅制度】超一线城市（北上广深）总监级别住宿上限为650元/晚。"
        "未经特批私自升舱产生的超额费用一律不予报销。"
    )

    print("🧪 实验 A：测试一份【100% 忠实可靠的回答】")
    answer_good = (
        "根据集团制度，总监在深圳出差每晚住宿上限为650元，且私自升舱产生的超额费用公司不予报销。"
    )
    score_a = calculate_faithfulness(context=standard_doc, answer=answer_good)
    print(f"📊 实验 A 忠实度得分: {score_a * 100:.1f}%\n")

    print("🧪 实验 B：测试一份【半真半假、夹带私货的幻觉回答】")
    # 这份回答里：650元是真的，但后半句“额外补贴300元洗浴费”纯属脑补！
    answer_hallucinated = (
        "总监在深圳住宿上限为650元/晚，此外公司为出差总监每日额外补贴300元洗浴养生津贴。"
    )
    score_b = calculate_faithfulness(
        context=standard_doc, answer=answer_hallucinated
    )
    print(f"📊 实验 B 忠实度得分: {score_b * 100:.1f}%\n")

