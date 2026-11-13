import json

from langgraph.constants import END

from schemas.state import ExpenseAuditState
from services.saga.payout_service import deduct_department_budget, compensate_department_budget

# 扣减预算
def deduct_budget_node(state:ExpenseAuditState):
    invoice = state.get("invoice",{})
    invoice_id = invoice.get("invoice_id","")
    dept = invoice.get("department","")
    amount = invoice.get("amount",0)
    res = deduct_department_budget(invoice_id,dept,amount)
    if res:
        return {
            "budget_deducted": True,
            # ❌ Python 中 list.append() 返回值永远是 None！
            "compensation_stack":
                ( state.get("compensation_stack") or []) + ["ROLLBACK_BUDGET"],
            "audit_trail": [f"T1 预扣部门 {dept} 预算 {amount} 元成功"]
        }
    else:
        return {
            "budget_deducted": False,
            "audit_trail": [f"T1 预扣部门 {dept} 预算失败：余额不足"]
        }
