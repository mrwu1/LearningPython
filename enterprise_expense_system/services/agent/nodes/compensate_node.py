from loguru import logger

from schemas.state import ExpenseAuditState
from services.saga.payout_service import compensate_department_budget


def compensate_node(state: ExpenseAuditState) -> dict:
    logger.info(f"执行回退逻辑")
    # 补偿栈是备忘录，里面存的是字符串命令（如 "ROLLBACK_BUDGET"）；
    # 扣款成功时只存标记："compensation_stack": ["ROLLBACK_BUDGET"]；
    # 只有在打款失败、流程真正走到 compensate 节点时，才去检查这个标记，执行真正的退款：
    invoice = state.get("invoice",{})
    invoice_id = invoice.get("invoice_id", "")
    dept = invoice.get("department","")
    amount = invoice.get("amount",0)

    stack = state.get("compensation_stack",[]).copy()
    while stack:
        action = stack.pop() # ✅✅✅
        if action == "ROLLBACK_BUDGET":
            compensate_department_budget(invoice_id,dept, amount)
    return {
        "compensation_stack":[],
        "final_status":"PAYOUT_FAILED_COMPENSATED",
        "audit_trail":["C1 Saga 逆向补偿完成：部门预算已原路退回"]
    }