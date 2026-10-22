from langchain_core.messages import SystemMessage, AIMessage, AIMessage
from loguru import logger
from app.core.llm import get_llm
from app.schemas.agent_state import SkyTakeoutState, SupervisorDecision
from app.services.agent.context_manager import prepare_trimmed_messages


async def supervisor_node(state: SkyTakeoutState) -> dict:
    """
    Central Supervisor Node:
    Dual-guard orchestration combining deterministic state-machine fast-path exit
    with dynamic LLM structured routing.
    """
    current_status = state.get("refund_status", "NONE")

    # -------------------------------------------------------------------------
    # 守卫 1: 确定性代码终态短路 (0ms, 0 Token，彻底消灭死循环)
    # -------------------------------------------------------------------------
    if current_status in ["APPROVED", "REJECTED"]:
        logger.info(
            f"[Supervisor Guard] 🛡️ Fast-path exit: Order refund already settled as '{current_status}'. "
            f"Bypassing LLM call."
        )
        return {"next_worker": "FINISH"}

    # -------------------------------------------------------------------------
    # 守卫 2: 确定性回复闭环短路 (专员已回复本轮对话，绝不重复分流，0ms, 0 Token)
    # -------------------------------------------------------------------------
    messages = state.get("messages", [])
    if messages and isinstance(messages[-1], AIMessage):
        specialist_name = getattr(messages[-1], "name", "specialist") or "specialist"
        logger.info(
            f"[Supervisor Guard] 🛡️ Fast-path exit: Specialist '{specialist_name}' "
            f"has answered the customer's query. Terminating current turn."
        )
        return {"next_worker": "FINISH"}

    # -------------------------------------------------------------------------
    # 守卫 2: 注入全局业务上下文的结构化路由
    # -------------------------------------------------------------------------
    supervisor_prompt = (
        "You are the Central Orchestration Supervisor for Sky Takeout.\n"
        "=== LIVE SYSTEM STATUS ===\n"
        f"- Target Order ID: {state.get('order_id', 'N/A')}\n"
        f"- Current Refund Status: {current_status}\n"
        f"- Refund Amount: ${state.get('refund_amount', 0.0):.2f}\n"
        "===========================\n\n"
        "Route customer query to the most qualified specialist:\n"
        "  1. 'dish_advisor': For meal suggestions, calories, taste, nutrition.\n"
        "  2. 'order_manager': For delivery tracking, ETA, courier location.\n"
        "  3. 'refund_officer': ONLY for unhandled refund requests or cold food complaints.\n"
        "  4. 'FINISH': If query is fully answered, greeting, or issue already resolved."
    )

    llm = get_llm(temperature=0.0)
    structured_llm = llm.with_structured_output(SupervisorDecision, method="function_calling")
    # decision: SupervisorDecision = await structured_llm.ainvoke(
    #     [SystemMessage(content=supervisor_prompt)] + state["messages"]
    # )
    # ✅ 修改后：接入修剪器，只送最近精简上下文
    optimized_prompt = prepare_trimmed_messages(
        system_prompt=supervisor_prompt,
        raw_messages=state["messages"]
    )
    decision: SupervisorDecision = await structured_llm.ainvoke(optimized_prompt)
    logger.info(f"[Supervisor] Routing decision -> '{decision.next_worker}' | Reason: {decision.reason}")
    return {"next_worker": decision.next_worker}


def route_from_supervisor(state: SkyTakeoutState) -> str:
    """Conditional edge router mapping next_worker to node name or __end__."""
    target = state.get("next_worker", "FINISH")
    if target == "FINISH" or not target:
        return "__end__"
    return target
