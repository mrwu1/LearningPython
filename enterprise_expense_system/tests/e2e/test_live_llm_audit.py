# 🔴【第 3 层：真实 LLM 端到端评估】(秒级 | 消耗 Token | 每日定时或发版前跑)
# 真实调用 DeepSeek 验证 Prompt 语义反舞弊与特批裁决准确性
from services.agent.graph.graph import build_graph
from services.saga.payout_service import department_budgets


def test_live_llm_rejects_fraudulent_shopping_card_description():
    """真实大模型端到端测试 1：金额虽未超标(88元)，但报销事由为购买超市购物卡/足浴按摩，LLM 必须一票否决 (REJECTED)"""
    app = build_graph()
    config = {"configurable": {"thread_id": "T-LIVE-FRAUD-01"}}
    res = app.invoke(
        {
            "invoice": {
                "invoice_id": "INV-LIVE-FRAUD-01",
                "employee_id": "EMP-09",
                "employee_name": "周八",
                "tier": "JUNIOR",
                "department": "TECH_DEPT",
                "city": "上海",
                "category": "MEAL",
                "amount": 88.0,
                "date": "2026-11-04",
                "description": "购买华润万家超市购物卡及晚间足浴按摩消费",
            }
        },
        config=config,
    )
    assert res["risk_verdict"] == "REJECTED"
    assert res["final_status"] == "REJECTED_BY_RISK_CONTROL"
    assert department_budgets["TECH_DEPT"] == 50000.0


def test_live_llm_flags_reasonable_over_limit_hotel():
    """真实大模型端到端测试 2：住宿超标(620元 > 450元)，但事由为展会满房客观原因，LLM 必须裁决为 FLAGGED_NEED_APPROVAL"""
    app = build_graph()
    config = {"configurable": {"thread_id": "T-LIVE-FLAG-01"}}
    app.invoke(
        {
            "invoice": {
                "invoice_id": "INV-LIVE-FLAG-01",
                "employee_id": "EMP-01",
                "employee_name": "张三",
                "tier": "JUNIOR",
                "department": "TECH_DEPT",
                "city": "上海",
                "category": "HOTEL",
                "amount": 620.0,
                "date": "2026-11-04",
                "description": "赴上海参加世界人工智能大会布展，场馆周边协议酒店全部满房，临时预订邻近商务酒店",
            }
        },
        config=config,
    )
    snapshot = app.get_state(config)
    assert snapshot.values["risk_verdict"] == "FLAGGED_NEED_APPROVAL"
    assert list(snapshot.next) == ["human_approval"]


def test_live_llm_auto_approves_normal_business_taxi():
    """真实大模型端到端测试 3：小额合规(65元)且事由真实合理，LLM 自动放行并完成打款 (PAID_SUCCESS)"""
    app = build_graph()
    config = {"configurable": {"thread_id": "T-LIVE-AUTO-01"}}
    res = app.invoke(
        {
            "invoice": {
                "invoice_id": "INV-LIVE-AUTO-01",
                "employee_id": "EMP-01",
                "employee_name": "张三",
                "tier": "JUNIOR",
                "department": "TECH_DEPT",
                "city": "北京",
                "category": "TAXI",
                "amount": 65.0,
                "date": "2026-11-04",
                "description": "从北京南站前往客户总部进行项目技术方案交付打车费",
            }
        },
        config=config,
    )
    assert res["risk_verdict"] == "AUTO_APPROVED"
    assert res["final_status"] == "PAID_SUCCESS"
    assert department_budgets["TECH_DEPT"] == 49935.0
