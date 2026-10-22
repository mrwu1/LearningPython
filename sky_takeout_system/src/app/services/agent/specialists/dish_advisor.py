from langchain_core.messages import AIMessage, SystemMessage

from app.core.database import AsyncSessionLocal
from app.core.llm import get_llm
from app.repositories.dish_repo import DishRepository
from app.schemas.agent_state import SkyTakeoutState


async def dish_advisor_worker(state: SkyTakeoutState) -> dict:
    """Specialist 1: Recommends delicious, healthy meals from real menu."""
    # request the real data from db
    menu_text=''
    async with AsyncSessionLocal() as session:
        available_dishes = await DishRepository.get_all_available(session)
        menu_items=[
            f"- {d.name}: Price=${d.price:.2f}, In-Stock={d.stock}, PrepTime={d.prep_time_minutes} mins"
            for d in available_dishes if d.stock > 0
        ]
        menu_text = "\n".join(menu_items)
    llm = get_llm(temperature=0.2)
    system_prompt = (
        "You are the Sky Takeout Gourmet Advisor.\n"
        "=== LIVE KITCHEN MENU & INVENTORY ===\n"
        f"{menu_text}\n"
        "======================================\n"
        "STRICT RULES:\n"
        "1. You MUST ONLY recommend dishes from the LIVE KITCHEN MENU above.\n"
        "2. Do NOT invent or mention dishes not listed above.\n"
        "3. State the exact dish name, price, and estimated prep time to the customer warmly in 2 concise sentences."
    )
    response = await llm.ainvoke([SystemMessage(content=system_prompt)] + state["messages"])
    # return {
    #     "messages": [AIMessage(content=f"[Dish Advisor]: {response.content}")],
    #     "next_worker": "FINISH"
    # }

    # 修改前：硬编码拼接字符串，容易污染上下文
    # "messages": [AIMessage(content=f"[Dish Advisor]: {response.content}")]

    # 修改后：内容保持纯净，通过 name 区分专员（LangSmith 和前端都能完美识别）
    clean_content = response.content.replace("[Dish Advisor]:", "").strip()
    return {
        "messages": [AIMessage(content=clean_content, name="dish_advisor")],
        "next_worker": "FINISH"
    }
