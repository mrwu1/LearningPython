# 专门测规则计算：一线/普通城市、各职级上限、周末无审批红线
from schemas.invoice import InvoiceItem
from services.rules.policy_checker import check_expense_policy


def _make_invoice(**overrides) -> InvoiceItem:
    base = {
        "invoice_id": "INV-TEST",
        "employee_id": "EMP-01",
        "employee_name": "李四",
        "tier": "JUNIOR",
        "department": "TECH_DEPT",
        "city": "北京",
        "category": "HOTEL",
        "amount": 400.0,
        "date": "2026-11-04",
    }
    base.update(overrides)
    return InvoiceItem.model_validate(base)


def test_hotel_super_vs_normal_city_and_soft_violation():
    """测试超一线与普通城市住宿标准，且超标属于可特批项 (is_hard_violation=False)"""
    # 北京(超一线) JUNIOR 上限 450 -> 400 元合规
    res_bj_ok = check_expense_policy(_make_invoice(city="北京", amount=400.0))
    assert res_bj_ok["is_compliant"] is True
    assert res_bj_ok["is_hard_violation"] is False

    # 同样 400 元在杭州(普通城市，上限 350) -> 超标 50 元，但非硬红线
    res_hz_over = check_expense_policy(_make_invoice(city="杭州", amount=400.0))
    assert res_hz_over["is_compliant"] is False
    assert res_hz_over["is_hard_violation"] is False
    assert res_hz_over["over_amount"] == 50.0

def test_weekend_meal_without_overtime_is_hard_violation():
        """测试周末餐饮无加班单：必须触发硬红线 (is_hard_violation=True)"""
        inv_no_ot = _make_invoice(category="MEAL", amount=80.0, is_weekend=True, has_overtime_approval=False)
        res_no_ot = check_expense_policy(inv_no_ot)
        assert res_no_ot["is_compliant"] is False
        assert res_no_ot["is_hard_violation"] is True

        # 有加班审批单：周末上限提升至 150 元 -> 120 元合规
        inv_with_ot = _make_invoice(category="MEAL", amount=120.0, is_weekend=True, has_overtime_approval=True)
        res_with_ot = check_expense_policy(inv_with_ot)
        assert res_with_ot["is_compliant"] is True
        assert res_with_ot["is_hard_violation"] is False


def test_long_distance_train_and_flight_limits():
    """测试高铁/机票按职级长途标准核算（JUNIOR 1000元），不与 150 元市内打车混淆"""
    inv_train = _make_invoice(category="TRAIN", amount=800.0, tier="JUNIOR")
    res_train = check_expense_policy(inv_train)
    assert res_train["is_compliant"] is True
    assert res_train["max_allowed"] == 1000