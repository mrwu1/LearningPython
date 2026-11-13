from langchain_core.messages import SystemMessage, HumanMessage
from loguru import logger
from pydantic import BaseModel, Field

from schemas.invoice import InvoiceItem
from services.rag.policy_knowledge_base import EnterprisePolicyKnowledgeBase
from utils.model import get_llm


class RAGPolicyDecision(BaseModel):
    """LLM 闭卷推导出的标准判决契约"""

    is_compliant: bool = Field(..., description="是否完全合规")
    is_hard_violation: bool = Field(
        ..., description="是否属于不可人工特批的严重硬违规"
    )
    max_allowed: float = Field(..., description="规章规定的允许最高上限金额")
    over_amount: float = Field(..., description="超标金额 (未超标填0.0)")
    violation_reason: str = Field(..., description="详细审计理由及条款依据")


def check_expense_policy_rag(invoice: InvoiceItem) -> dict:
    """调用 RAG 检索企业最新政策并判定发票合规性。

    返回格式与原 policy_checker.check_expense_policy 100% 对齐。
    """
    kb = EnterprisePolicyKnowledgeBase()
    # 1. 动态检索最匹配的规章条款              - [ ‼️‼️‼️：RAG here ]
    context = kb.retrieve_relevant_policy(
        category=invoice.category.value,
        city=invoice.city or "全国",
        description=invoice.description or "",
    )
    logger.info(f"‼️【Retriever output context: {context}】")

    # 2. 调用 LLM 结合条款进行闭卷推导
    system_prompt = (
        "你是一家企业智能财务中台的合规审计专家。\n"
        "请严格依据参考制度条款，对员工申报的发票执行合规判定：\n"
        "1. is_compliant: 发票金额 <= 规章上限 且无违规项；\n"
        "2. max_allowed: 规章中该职级/城市的基准上限；\n"
        "3. over_amount: max(0.0, 发票金额 - max_allowed)；\n"
        "4. is_hard_violation: 若存在私自升舱、周末加班无审批单等触碰红线的行为，标为 True；常规超标标为 False；\n"
        "5. violation_reason: 若违规或超标，必须陈述违规事实与条款要求；若合规填空字符串。"
    )

    user_prompt = (
        f"【参考制度条款】：\n{context}\n\n"
        f"【待审计发票】：\n"
        f"- 消费类目: {invoice.category.value}\n"
        f"- 消费金额: {invoice.amount} 元\n"
        f"- 消费城市: {invoice.city}\n"
        f"- 员工职级: {invoice.tier.value}\n"
        f"- 是否周末: {invoice.is_weekend}\n"
        f"- 是否有加班单: {invoice.has_overtime_approval}\n"
        f"- 备注说明: {invoice.description}\n"
    )

    llm = get_llm()
    evaluator = llm.with_structured_output(
        schema=RAGPolicyDecision, method="function_calling"
    )
    decision: RAGPolicyDecision = evaluator.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )

    result = decision.model_dump()
    logger.info(
        f"🔍 [RAG 动态政策审计] 单号={invoice.invoice_id} | 合规={result['is_compliant']} | "
        f"上限={result['max_allowed']} | 超标={result['over_amount']}"
    )
    return result