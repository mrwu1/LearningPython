"""lesson_13_ragas_evaluation.py

    阶段四 · 4.3 工业级 RAGAS 自动化量化评估体系
    核心目标：
    掌握 RAG 黄金三元组三大核心指标的量化计算：
    1. Faithfulness (事实忠实度) -> 测生成无幻觉
    2. Context Recall (上下文召回率) -> 测检索无遗漏
    3. A
"""
from langchain_core.messages import SystemMessage, HumanMessage
from loguru import logger
from pydantic import BaseModel, Field

from utils.model import get_llm


# 尺子 3：相关度契约
class RelevanceEvaluation(BaseModel):
        is_relevant: bool = Field(
            ..., description="回答是否正面且直接回答了用户的核心提问"
        )
        score: float = Field(
            ..., description="切题契合度评分 (0.0 ~ 1.0)，废话或答非所问扣分"
        )
        reason: str = Field(..., description="判定理由")


def calculate_answer_relevance(question: str, answer: str) -> float:
    """尺子 3：计算回答相关度 (0.0 ~ 1.0)"""
    llm = get_llm()
    grader = llm.with_structured_output(
        schema=RelevanceEvaluation, method="function_calling"
    )
    system_prompt = (
        "你是一位问答切题度评估裁判。\n"
        "评估【回答】是否直接针对【用户提问】的诉求展开，有无避重就轻、绕弯子或答非所问。\n"
        "直接切题打 0.9~1.0；答非所问或废话连篇打 0.0~0.4。"
    )
    report: RelevanceEvaluation = grader.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=f"【用户提问】：\n{question}\n\n【待评估回答】：\n{answer}"
            ),
        ]
    )
    logger.info(f"report: {report}")
    return round(report.score, 4)


if __name__ == "__main__":
    # 用户提问（包含两个明确的诉求：金额多少？能否报销？）
    question = (
        "总监去深圳出差，每晚酒店报销上限是多少？私自升舱能报吗？"
    )

    print("=" * 80)
    print("🧪 实验 E：校准【开门见山、直接切题的优质回答 (预期 95%~100%)】")
    # 针对两个核心问题，直接给出数字和明确结论，不绕弯子
    answer_relevant = (
        "总监在深圳出差每晚住宿上限为650元。若私自升舱且未经特批，产生的超额费用不予报销。"
    )
    score_e = calculate_answer_relevance(
        question=question, answer=answer_relevant
    )
    print(f"📊 实验 E 相关度得分: {score_e * 100:.1f}%\n")

    print(
        "🧪 实验 F：校准【避重就轻、废话连篇的跑题回答 (预期 0%~20%)】"
    )
    # 虽然每一句都是大实话、没有造假，但通篇废话，完全回避了金额和升舱！
    answer_evasive = (
        "深圳是一座气候宜人的现代化海滨大都市。公司倡导大家在差旅期间注意人身财产安全，"
        "践行绿色低碳环保出行，发票请按财务规定平整粘贴。"
    )
    score_f = calculate_answer_relevance(
        question=question, answer=answer_evasive
    )
    print(f"📊 实验 F 相关度得分: {score_f * 100:.1f}%\n")
