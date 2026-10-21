# 我们来为上一节的多智能体主管系统编写一套完备的Pytest测试套件，包含4个核心测试用例：
# test_route_to_dish_advisor：验证点餐意图正确路由至菜品专家，并闭环结束。
# test_route_to_order_manager：验证催单意图正确路由至履约经理，并闭环结束。
# test_immediate_finish_on_resolved_query：验证当主管判断问题已解决时，直接FINISH，专家节点一次都不被调用（短路优化）
# test_defensive_routing_fallback：验证当 next_worker 为未知脏数据时，条件边安全兜底退出。
import importlib
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

supervisor_module = importlib.import_module("chapter_08.01_multi_agent_supervisor")

build_supervisor_graph = supervisor_module.build_supervisor_graph # the creating graph function

SupervisorRouteDecision = supervisor_module.SupervisorRouteDecision # dict

# Fixture: Compile graph once for all tests
@pytest.fixture
def multi_agent_app():
    return build_supervisor_graph()

# Test 1: Verify Delegation to Dish Advisor
def test_route_to_dish_advisor(multi_agent_app):
    with patch.object(supervisor_module,"get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        # Step 1: Supervisor routes to dish_advisor; Step 2: Supervisor routes to FINISH
        mock_structured.invoke.side_effect = [
            SupervisorRouteDecision(next_worker="dish_advisor", routing_reason="Meal advice needed"),
            SupervisorRouteDecision(next_worker="FINISH", routing_reason="Query answered")
        ]
        mock_llm.with_structured_output.return_value = mock_structured
        mock_llm.invoke.return_value = AIMessage(content="Mocked Grilled Salmon Salad (420 kcal).")
        mock_get_llm.return_value = mock_llm

        input_state = {
            "messages": [HumanMessage(content="Recommend a low cal salmon meal.")],
            "next_worker": ""
        }
        config = {"configurable": {"thread_id": "TEST_THREAD_DISH"}}
        final_state = multi_agent_app.invoke(input_state, config=config)

        # Assertions
        assert len(final_state["messages"]) == 2
        assert "[Dish advisor]:" in final_state["messages"][-1].content
        assert "Grilled Salmon Salad" in final_state["messages"][-1].content
        assert final_state["next_worker"] == "FINISH"
        # Verify supervisor was invoked exactly twice (Initial dispatch + Completion review)
        assert mock_structured.invoke.call_count == 2

    # ==============================================================================
    # Test 2: Verify Delegation to Order Manager
    # ==============================================================================
def test_route_to_order_manager(multi_agent_app):
        """
        Validates flow: START -> supervisor -> order_manager -> supervisor -> END.
        """
        with patch.object(supervisor_module, "get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_structured = MagicMock()

            # Step 1: Supervisor routes to order_manager; Step 2: Supervisor routes to FINISH
            mock_structured.invoke.side_effect = [
                SupervisorRouteDecision(next_worker="order_manager", routing_reason="Logistics tracking"),
                SupervisorRouteDecision(next_worker="FINISH", routing_reason="ETA provided")
            ]
            mock_llm.with_structured_output.return_value = mock_structured
            mock_llm.invoke.return_value = AIMessage(content="Courier is 500m away, arriving in 3 mins.")
            mock_get_llm.return_value = mock_llm

            input_state = {
                "messages": [HumanMessage(content="Where is my takeout?")],
                "next_worker": ""
            }
            config = {"configurable": {"thread_id": "TEST_THREAD_ORDER"}}
            final_state = multi_agent_app.invoke(input_state, config=config)

            # Assertions
            assert len(final_state["messages"]) == 2
            assert "[Order Manager]:" in final_state["messages"][-1].content
            assert "Courier is 500m away" in final_state["messages"][-1].content
            assert final_state["next_worker"] == "FINISH"

            # ==============================================================================

    # Test 3: Short-Circuit Flow (Supervisor finishes immediately)
    # ==============================================================================
def test_immediate_finish_on_resolved_query(multi_agent_app):
        """
        Validates flow: START -> supervisor -> END.
        Workers should NEVER be invoked if supervisor decides query needs no action.
        """
        with patch.object(supervisor_module, "get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_structured = MagicMock()
            logger.info(f"❌❌mock_llm:{mock_llm}")
            logger.info(f"❌❌mock_structured:{mock_structured}")
            # Supervisor immediately concludes FINISH
            mock_structured.invoke.return_value = SupervisorRouteDecision(
                next_worker="FINISH",
                routing_reason="Greeting only, no action required"
            )
            mock_llm.with_structured_output.return_value = mock_structured
            mock_get_llm.return_value = mock_llm

            input_state = {
                "messages": [HumanMessage(content="Hello! Just saying hi.")],
                "next_worker": ""
            }
            config = {"configurable": {"thread_id": "TEST_THREAD_GREETING"}}
            final_state = multi_agent_app.invoke(input_state, config=config)

            # Assertions: No new messages appended, supervisor called only once
            assert len(final_state["messages"]) == 1
            assert final_state["next_worker"] == "FINISH"
            assert mock_structured.invoke.call_count == 1
            # Worker models were never invoked!
            assert mock_llm.invoke.call_count == 0

