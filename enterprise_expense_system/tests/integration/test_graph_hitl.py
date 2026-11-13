# 专门测人机协同：interrupt() 挂起快照校验、Command(resume) 同意/驳回
from langgraph.types import Command

from tests.integration.test_graph_routing import _FakeStructuredLLM
from services.agent.graph.graph import build_graph
from services.saga.payout_service import department_budgets


def test_hitl_interrupt_and_manager_approve_or_reject(monkeypatch):
    """测试超标发票触发 interrupt() 挂起，以及主管同意/驳回两条恢复链路"""
    fake_llm = _FakeStructuredLLM(
        response={"risk_verdict": "FLAGGED_NEED_APPROVAL", "reason": "展会期间满房超标，建议主管复核"}
    )
    monkeypatch.setattr("services.agent.nodes.risk_assessment_node.get_llm", lambda: fake_llm)

    app = build_graph()

    # 场景 A：主管审批通过 -> 扣减预算并打款成功 (PAID_SUCCESS)
    cfg_approve = {"configurable": {"thread_id": "T-HITL-APPROVE"}}
    app.invoke(
        {
            "invoice": {
                "invoice_id": "INV-HITL-01",
                "employee_id": "EMP-01",
                "employee_name": "张三",
                "tier": "JUNIOR",
                "department": "TECH_DEPT",
                "city": "北京",
                "category": "HOTEL",
                "amount": 750.0,
                "date": "2026-11-04",
            }
        },
        config=cfg_approve,
    )
    # 断言上半场已暂停在 human_approval，且预算尚未扣减
    snap_paused = app.get_state(cfg_approve)
    assert list(snap_paused.next) == ["human_approval"]
    assert department_budgets["TECH_DEPT"] == 50000.0

    # 主管调用 Command(resume=...) 同意报销
    res_approved = app.invoke(
        Command(resume={"status": "approved", "reason": "展会房源紧张，特批实报实销"}),
        config=cfg_approve,
    )
    assert res_approved["final_status"] == "PAID_SUCCESS"
    assert department_budgets["TECH_DEPT"] == 49250.0

    # 场景 B：主管审批驳回 -> 归档为 REJECTED_BY_MANAGER，不扣一分钱预算
    cfg_reject = {"configurable": {"thread_id": "T-HITL-REJECT"}}
    app.invoke(
        {
            "invoice": {
                "invoice_id": "INV-HITL-02",
                "employee_id": "EMP-02",
                "employee_name": "李四",
                "tier": "JUNIOR",
                "department": "SALES_DEPT",
                "city": "上海",
                "category": "HOTEL",
                "amount": 800.0,
                "date": "2026-11-04",
            }
        },
        config=cfg_reject,
    )
    res_rejected = app.invoke(
        Command(resume={"status": "rejected", "reason": "非核心展区，拒绝超标住宿"}),
        config=cfg_reject,
    )
    assert res_rejected["final_status"] == "REJECTED_BY_MANAGER"
    assert department_budgets["SALES_DEPT"] == 30000.0