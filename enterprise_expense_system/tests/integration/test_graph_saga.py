# 专门测异常恢复：模拟银行 500 故障触发 compensate 节点回滚闭环
from fastapi.testclient import TestClient

from api.main import app as fastapi_app
from services.saga.payout_service import department_budgets, budget_deducted_ledger
from tests.integration.test_graph_routing import _FakeStructuredLLM


def test_bank_failure_triggers_saga_rollback_via_fastapi(monkeypatch):
    """通过 FastAPI 接口测试：银行网关故障时，Saga 自动逆向退还部门预算"""
    fake_llm = _FakeStructuredLLM(
        response={"risk_verdict": "AUTO_APPROVED", "reason": "小额合规市内交通"}
    )
    monkeypatch.setattr("services.agent.nodes.risk_assessment_node.get_llm", lambda: fake_llm)

    client = TestClient(fastapi_app)
    resp = client.post(
        "/api/v1/expenses/submit",
        json={
            "invoice": {
                "invoice_id": "INV-SAGA-500",
                "employee_id": "EMP-01",
                "employee_name": "赵六",
                "tier": "JUNIOR",
                "department": "TECH_DEPT",
                "city": "北京",
                "category": "TAXI",
                "amount": 100.0,
                "date": "2026-11-04",
            },
            "simulate_bank_failure": True,  # 开启银行故障模拟
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["workflow_status"] == "COMPLETED"
    assert data["final_status"] == "PAYOUT_FAILED_COMPENSATED"
    # 验证 T1 扣掉的 100 元已被 C1 原路退回，账本无残留！
    assert department_budgets["TECH_DEPT"] == 50000.0
    assert "INV-SAGA-500" not in budget_deducted_ledger


def test_fastapi_hitl_submit_and_approve_and_duplicate_guard(monkeypatch):
    """通过 FastAPI 接口测试：提交挂起 -> 重复提交报409 -> 主管审批通过 -> 重复审批报409"""
    fake_llm = _FakeStructuredLLM(
        response={"risk_verdict": "FLAGGED_NEED_APPROVAL", "reason": "超标待主管特批"}
    )
    monkeypatch.setattr("services.agent.nodes.risk_assessment_node.get_llm", lambda: fake_llm)

    client = TestClient(fastapi_app)
    payload = {
        "invoice": {
            "invoice_id": "INV-API-HITL-01",
            "employee_id": "EMP-01",
            "employee_name": "孙七",
            "tier": "JUNIOR",
            "department": "SALES_DEPT",
            "city": "深圳",
            "category": "HOTEL",
            "amount": 600.0,
            "date": "2026-11-04",
        }
    }

    # 1. 初次提交：挂起等待主管审批
    r1 = client.post("/api/v1/expenses/submit", json=payload)
    assert r1.status_code == 200
    assert r1.json()["workflow_status"] == "PENDING_APPROVAL"
    assert r1.json()["interrupt_payload"]["invoice"]["amount"] == 600.0

    # 2. 幂等守卫：重复提交同一发票必须返回 HTTP 409 Conflict
    r_dup = client.post("/api/v1/expenses/submit", json=payload)
    assert r_dup.status_code == 409

    # 3. 主管调用 /approve 同意特批 -> 走完打款
    r_approve = client.post(
        "/api/v1/expenses/INV-API-HITL-01/approve",
        json={"status": "approved", "reason": "深圳客户紧急拜访，同意报销"},
    )
    assert r_approve.status_code == 200
    assert r_approve.json()["workflow_status"] == "COMPLETED"
    assert r_approve.json()["final_status"] == "PAID_SUCCESS"
    assert department_budgets["SALES_DEPT"] == 29400.0

    # 4. 状态守卫：对已完结工单再次点击 /approve 必须返回 HTTP 409 Conflict
    r_approve_again = client.post(
        "/api/v1/expenses/INV-API-HITL-01/approve",
        json={"status": "approved", "reason": "手滑连点第二次"},
    )
    assert r_approve_again.status_code == 409