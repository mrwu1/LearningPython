from schemas.state import ExpenseAuditState
from services.saga.payout_service import execute_bank_transfer


# 执行银行转账 节点
def execute_bank_transfer_node(state:ExpenseAuditState)->dict:
    invoice = state.get("invoice",{})
    invoice_id = invoice.get("invoice_id", "")
    employee_id = invoice.get("employee_id","")
    amount = invoice.get("amount",0.0)
    simulate = state.get("simulate_bank_failure", False)

    res = execute_bank_transfer(invoice_id,employee_id,amount,simulate)
    is_ok = bool(res.get("success"))
    return {
        "bank_transfer_success": is_ok,
        "audit_trail": [f"T2 银行打款结果: success={is_ok}"]
    }