from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from app.core.llm import get_llm
from app.schemas.agent_state import SkyTakeoutState
from app.services.agent.tools.courier_tool import query_courier_telemetry


async def order_manager_worker(state: SkyTakeoutState) -> dict:
    """Specialist 2: Queries real-time courier telemetry from MySQL and reassures customer."""
    order_number = state.get("order_id", "ORD-UNKNOWN")
    # 调用生产级 Tool (从 MySQL 真实 orders 表查询)
    telemetry = await query_courier_telemetry.ainvoke({"order_number": order_number})

    llm = get_llm(temperature=0.0)
    prompt = [
        SystemMessage(
            content=f"You are the Sky Takeout Logistics Manager. Real-time courier telemetry: '{telemetry}'. "
                    f"Reassure customer warmly in 2 sentences."
        ),
        HumanMessage(content=state["messages"][-1].content)
    ]
    response = await llm.ainvoke(prompt)
    clean_content = response.content.replace("[Order Manager]:", "").strip()
    return {
        "messages": [AIMessage(content=clean_content, name="order_manager")],
        "next_worker": "FINISH"
    }
