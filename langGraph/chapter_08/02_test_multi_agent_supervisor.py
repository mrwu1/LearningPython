"""
================================================================================
【LangGraph 阶段八：生产级多智能体协同架构】第 2 课：多智能体主管系统 Pytest 自动化测试套件
================================================================================
【核心学习目标】：
1. 掌握多智能体图的单元与集成测试方法论（Mocking & Testing Multi-Agent）：
   - 核心难点：不能在单元测试中直接调用真实的外部大模型 API（费用昂贵、响应缓慢、不可控且容易断网报错）；
   - 解决方案：使用 `unittest.mock.patch` 对 `get_llm` 进行精准打桩（Mock），模拟不同分支的大模型推理响应。
2. 掌握核心测试用例矩阵：
   - 用例 1（`test_route_to_dish_advisor`）：验证点餐诉求能否被 Supervisor 正确路由至菜品专家，并闭环结束；
   - 用例 2（`test_route_to_order_manager`）：验证催单诉求能否被正确路由至履约经理，并闭环结束；
   - 用例 3（`test_immediate_finish_on_resolved_query`）：验证打招呼或无需派单的问题直接触发 FINISH 短路（Short-Circuit），任何专家节点都不会被误触发。
3. 掌握图执行状态断言（Assertions）：验证对话历史消息长度、专家标签、Supervisor 的被调用频次。
================================================================================
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from loguru import logger

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 动态导入上一节课的主管模块
supervisor_module = importlib.import_module("chapter_08.01_multi_agent_supervisor")
build_supervisor_graph = supervisor_module.build_supervisor_graph
SupervisorRouteDecision = supervisor_module.SupervisorRouteDecision


# ==============================================================================
# Pytest Fixture：全局编译图实例
# ==============================================================================
@pytest.fixture
def multi_agent_app():
    """在所有测试用例之间复用编译好的图对象，提升测试执行速度。"""
    return build_supervisor_graph()


# ==============================================================================
# 测试用例 1：验证美食品鉴顾问分支的路由与闭环
# ==============================================================================
def test_route_to_dish_advisor(multi_agent_app):
    """
    【测试验证完整链路】：
    START -> supervisor (指派 dish_advisor) -> dish_advisor (作答) -> supervisor (验收判定 FINISH) -> END。
    """
    with patch.object(supervisor_module, "get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_structured = MagicMock()

        # 【核心 Mock 技巧：side_effect 模拟时序调用】
        # 第一次调用 supervisor：分发给 dish_advisor；
        # 第二次调用 supervisor（专家答完回传时）：主管验收通过，下达 FINISH 终结。
        mock_structured.invoke.side_effect = [
            SupervisorRouteDecision(next_worker="dish_advisor", routing_reason="需要美食品鉴建议"),
            SupervisorRouteDecision(next_worker="FINISH", routing_reason="问题已解答完毕")
        ]
        mock_llm.with_structured_output.return_value = mock_structured
        # 模拟垂直专家的答复内容
        mock_llm.invoke.return_value = AIMessage(content="推荐香煎三文鱼温沙拉，热量仅 420 大卡。")
        mock_get_llm.return_value = mock_llm

        input_state = {
            "messages": [HumanMessage(content="推荐一份低卡的三文鱼餐食。")],
            "next_worker": ""
        }
        config = {"configurable": {"thread_id": "TEST_THREAD_DISH"}}
        final_state = multi_agent_app.invoke(input_state, config=config)

        # ----------------------------------------------------------------------
        # 严格断言结果
        # ----------------------------------------------------------------------
        # 1. 消息列表中应该有 2 条消息（1 条用户提问 + 1 条专家回复）
        assert len(final_state["messages"]) == 2
        # 2. 消息内容必须来自 dish_advisor
        assert "【美食品鉴专家】" in final_state["messages"][-1].content
        assert "香煎三文鱼" in final_state["messages"][-1].content
        # 3. 最终流转状态收敛为 FINISH
        assert final_state["next_worker"] == "FINISH"
        # 4. 验证 Supervisor 被精确调用了两次（首轮调度 + 尾轮验收）
        assert mock_structured.invoke.call_count == 2


# ==============================================================================
# 测试用例 2：验证物流履约管家分支的路由与闭环
# ==============================================================================
def test_route_to_order_manager(multi_agent_app):
    """
    【测试验证完整链路】：
    START -> supervisor (指派 order_manager) -> order_manager (查询物流) -> supervisor (判定 FINISH) -> END。
    """
    with patch.object(supervisor_module, "get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_structured = MagicMock()

        # 模拟 Supervisor 的两次决策
        mock_structured.invoke.side_effect = [
            SupervisorRouteDecision(next_worker="order_manager", routing_reason="需要查询骑手物流轨迹"),
            SupervisorRouteDecision(next_worker="FINISH", routing_reason="已向顾客清晰告知送达时间")
        ]
        mock_llm.with_structured_output.return_value = mock_structured
        mock_llm.invoke.return_value = AIMessage(content="骑手距离您 500 米，预计 3 分钟内送达。")
        mock_get_llm.return_value = mock_llm

        input_state = {
            "messages": [HumanMessage(content="我的外卖到哪了？急！")],
            "next_worker": ""
        }
        config = {"configurable": {"thread_id": "TEST_THREAD_ORDER"}}
        final_state = multi_agent_app.invoke(input_state, config=config)

        # 断言结果
        assert len(final_state["messages"]) == 2
        assert "【履约调度专家】" in final_state["messages"][-1].content
        assert "500 米" in final_state["messages"][-1].content
        assert final_state["next_worker"] == "FINISH"
        assert mock_structured.invoke.call_count == 2


# ==============================================================================
# 测试用例 3：短路分支验证（主管直接判断无需派单）
# ==============================================================================
def test_immediate_finish_on_resolved_query(multi_agent_app):
    """
    【短路优化验证】：
    当用户仅仅发送打招呼消息时，Supervisor 应直接决策 FINISH，
    任何下游专家节点一次都不会被调用，从而节约算力。
    """
    with patch.object(supervisor_module, "get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_structured = MagicMock()

        # 主管直接返回 FINISH
        mock_structured.invoke.return_value = SupervisorRouteDecision(
            next_worker="FINISH",
            routing_reason="仅为常规问候，无需下发给专业业务节点"
        )
        mock_llm.with_structured_output.return_value = mock_structured
        mock_get_llm.return_value = mock_llm

        input_state = {
            "messages": [HumanMessage(content="你好！我只是路过打个招呼。")],
            "next_worker": ""
        }
        config = {"configurable": {"thread_id": "TEST_THREAD_GREETING"}}
        final_state = multi_agent_app.invoke(input_state, config=config)

        # 断言：消息长度依然为 1（没有触发任何新回复），主管只调用了 1 次，专家的 LLM 调用次数为 0
        assert len(final_state["messages"]) == 1
        assert final_state["next_worker"] == "FINISH"
        assert mock_structured.invoke.call_count == 1
        assert mock_llm.invoke.call_count == 0  # 证明没有浪费任何专家算力！
