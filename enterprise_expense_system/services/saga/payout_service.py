# 模拟企业部门差旅预算数据库（初始额度）
from loguru import logger

department_budgets = {
    "TECH_DEPT": 50000.00,
    "SALES_DEPT": 30000.00
}
# 幂等账本：记录已扣减预算的 invoice_id 与已打款的交易凭证
budget_deducted_ledger: set[str] = set()
bank_transfer_ledger: dict[str, dict] = {}

# T1：扣减部门预算
def deduct_department_budget(invoice_id:str,department:str,amount:float):
    # 幂等拦截 invoice_id
    if invoice_id  in budget_deducted_ledger:
        logger.warning(f"[幂等拦截] 发票 {invoice_id} 已扣减过部门预算，跳过重复扣减")
        return True

    budget = department_budgets.get(department,0)
    logger.info(f"准备预扣部门预算: dept={department}, 当前余额={budget}, 扣减金额={amount}")
    if budget >= amount:
        department_budgets[department] = round(budget-amount,2)
        budget_deducted_ledger.add(invoice_id)
        return True
    logger.error(f"部门 {department} 预算不足！当前余额={budget}, 需要={amount}")
    return False

#C1: 补偿 t1
# ❌ • 正向扣预算成功时，invoice_id 被加进了 budget_deducted_ledger。
#   • 当银行打款失败、需要回滚退钱时，你的代码看到 invoice_id in budget_deducted_ledger 为真，直接 return True
#   跳过了！导致预算永远退不回来！
def compensate_department_budget(invoice_id:str,department:str,amount:float):
    if invoice_id not in budget_deducted_ledger:
        logger.warning(f"[幂等补偿跳过] 发票 {invoice_id} 未曾扣减预算或已回滚")
        return True
    logger.info(f"执行 Saga 补偿机制：退还部门 {department} 预算 {amount} 元")
    department_budgets[department] = round(department_budgets.get(department, 0.0) + amount, 2)
    budget_deducted_ledger.remove(invoice_id)
    return True

# T2：模拟银企直联对公打款接口
def execute_bank_transfer(invoice_id: str,employee_id:str,amount:float,simulate_failure:bool = False):
    if invoice_id in bank_transfer_ledger:
        logger.warning(f"[幂等拦截] 发票 {invoice_id} 已完成打款，直接返回历史回执")
        return bank_transfer_ledger[invoice_id]

    logger.info(f"准备进行银行打款: invoice={invoice_id}, emp={employee_id}, amount={amount}")
    if simulate_failure:
        return{
            "success":False,
            "error": "BANK_GATEWAY_TIMEOUT"
        }
    receipt= {
        "success":True,
        "tx_id": f"TX-BANK-{invoice_id}",
        "amount": amount,
    }
    bank_transfer_ledger[invoice_id] = receipt
    return receipt