from loguru import logger

from schemas.invoice import InvoiceItem
from schemas.state import ExpenseAuditState
from services.rag.rag_policy_checker import check_expense_policy_rag


def check_invoice_policy_node(state: ExpenseAuditState)->dict:
    raw_invoice = state.get("invoice", {})

    ### ❌ 严重缺陷 1：【Pydantic 契约彻底沦为摆设（死代码）】 ✅ model_validate
    # 1. 强类型校验：如果 amount <= 0 或枚举非法，Pydantic 当场拦截抛错
    invoice_item = InvoiceItem.model_validate(raw_invoice) # 校验，并且返回一个 实例对象 ⚠️

    # 2. 传入真实的 InvoiceItem 实例
    res = check_expense_policy_rag(invoice_item)
    # return {
    #     "is_compliant": is_compliant,  # 是否完全合规（没有超标，且无违规项）
    #     "max_allowed": max_allowed,  # 该职级/城市允许报销的最高上限
    #     "over_amount": over_amount,  # 超标金额（若未超标则为 0.0）
    #     "violation_reason": violation_reason  # 违规/超标原因说明（若合规可为空字符串 ""）
    # }
    logger.info(f"差旅政策合规检查结果：{res}")
    return {
        "invoice": invoice_item.model_dump(),# ✅ 实例对象 转为dict
        "manager_decision": None,  # ✅ 入口重置瞬态字段，防止同一 thread_id 状态串味
        "budget_deducted": None,
        "bank_transfer_success": None,
        "compensation_stack": [],
        "policy_result":res,
        "audit_trail":[f"政策核验完成: is_compliant={res['is_compliant']}, over_amount={res['over_amount']}"]
    }
