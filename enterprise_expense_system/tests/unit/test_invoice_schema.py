# 专门测 Pydantic 边界：负数金额报错、非法枚举拦截、默认值
import pytest
from pydantic import ValidationError

from schemas.invoice import InvoiceItem, ManagerDecision


def test_valid_invoice_defaults():
    raw={
        "invoice_id": "INV-001",
        "employee_id": "EMP-01",
        "employee_name": "张三",
        "tier": "JUNIOR",
        "department": "TECH_DEPT",
        "city": "北京",
        "category": "TAXI",
        "amount": 85.0,
        "date": "2026-11-04",
    }
    item = InvoiceItem.model_validate(raw)
    assert item.amount == 85.0
    assert item.is_weekend is False
    assert item.has_overtime_approval is False
    assert item.description == "日常因公差旅消费"

@pytest.mark.parametrize("invalid_amount", [0, -0.01, -500])
def test_invoice_rejects_non_positive_amount(invalid_amount):
    """测试 gt=0 约束：零元或负数发票必须当场抛 ValidationError"""
    raw = {
        "invoice_id": "INV-ERR",
        "employee_id": "EMP-01",
        "employee_name": "张三",
        "tier": "JUNIOR",
        "department": "TECH_DEPT",
        "city": "上海",
        "category": "MEAL",
        "amount": invalid_amount,
        "date": "2026-11-04",
    }
    with pytest.raises(ValidationError):
        InvoiceItem.model_validate(raw)


def test_manager_decision_blocks_typo():
    """测试人工审批契约：拼写错误（如把 approved 写成 approve）必须当场拦截"""
    with pytest.raises(ValidationError):
        ManagerDecision.model_validate({"status": "approve", "reason": "同意"})

    valid = ManagerDecision.model_validate({"status": "approved"})
    assert valid.status == "approved"
    assert valid.reason == "主管未填写具体意见"



