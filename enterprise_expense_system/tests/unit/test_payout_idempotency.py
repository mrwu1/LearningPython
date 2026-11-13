# 专门测财务服务：扣预算、退预算、相同 invoice_id 幂等防重扣
from services.saga.payout_service import deduct_department_budget, department_budgets, compensate_department_budget


def test_budget_deduction_idempotency_and_float_precision():
    """测试预算扣减幂等性与浮点数两位小数精度保护"""
    # 连续扣减带分位的金额：50000.00 - 199.99 = 49800.01
    assert deduct_department_budget("INV-101", "TECH_DEPT", 199.99) is True
    assert department_budgets["TECH_DEPT"] == 49800.01

    # 同一 invoice_id 重复调用：触发幂等拦截，余额绝不二次扣减！
    assert deduct_department_budget("INV-101", "TECH_DEPT", 199.99) is True
    assert department_budgets["TECH_DEPT"] == 49800.01

def test_saga_compensation_restores_budget_and_is_idempotent():
        """测试 Saga 逆向补偿：原路退回预算并移除账本标记，重复补偿幂等安全"""
        deduct_department_budget("INV-102", "SALES_DEPT", 1000.0)
        assert department_budgets["SALES_DEPT"] == 29000.0

        # 第一次补偿：退回 1000 元，恢复至 30000.0
        assert compensate_department_budget("INV-102", "SALES_DEPT", 1000.0) is True
        assert department_budgets["SALES_DEPT"] == 30000.0

        # 第二次重复补偿同一张发票：幂等跳过，绝不多退钱！
        assert compensate_department_budget("INV-102", "SALES_DEPT", 1000.0) is True
        assert department_budgets["SALES_DEPT"] == 30000.0


def test_exact_boundary_budget_deduction():
    """测试余额刚好等于报销金额 (budget == amount) 时的边界扣减"""
    assert deduct_department_budget("INV-ALL", "SALES_DEPT", 30000.0) is True
    assert department_budgets["SALES_DEPT"] == 0.0