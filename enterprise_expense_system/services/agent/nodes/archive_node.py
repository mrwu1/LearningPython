from loguru import logger

from schemas.state import ExpenseAuditState


# ✅：内部根据上游留下的状态痕迹做精准定性
def archive_node(state: ExpenseAuditState) -> dict:
    logger.info("报销被驳回或预算不足，归档终止")
    # 情况 1：走到了扣预算阶段，但部门预算不足（注意用 is False 判断，因为未走到扣预算时该字段为 None）
    if state.get("budget_deducted") is False:
        status = "ABORTED_INSUFFICIENT_BUDGET"
        msg = "流程中止归档：部门差旅预算池余额不足，待财务追加预算"
    # 情况 2：经过了主管人工审批，被主管驳回
    elif state.get("manager_decision"):
        reason = state.get("manager_decision").get("reason","没有理由")
        status = "REJECTED_BY_MANAGER"
        msg = f"流程终止归档：主管人工审批驳回 (理由: {reason})"
    # 情况 3：初审直接触发反舞弊红线或风控驳回
    else:
        status = "REJECTED_BY_RISK_CONTROL"
        msg = "流程终止归档：初审触发风控反舞弊红线，一票否决"
    return {
        "final_status":status,
        "audit_trail": [msg]
    }