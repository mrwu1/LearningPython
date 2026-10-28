from typing import Optional

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.store.base import BaseStore
from langgraph.types import StreamWriter
from loguru import logger

from app.core.database import AsyncSessionLocal
from app.core.llm import get_llm
from app.repositories.dish_repo import DishRepository
from app.schemas.agent_state import SkyTakeoutState
from app.schemas.user_profile import UserDietaryProfile
from app.services.agent.context_manager import prepare_trimmed_messages


async def dish_advisor_worker(
        state: SkyTakeoutState,
        store:Optional[BaseStore] = None,
        writer: Optional[StreamWriter] = None  # 👈 注入 StreamWriter
) -> dict:
    """Specialist 1: Recommends delicious, healthy meals from real menu."""
    effective_user_id = state.get("user_id", "GUEST")
    # 1. 跨会话长期记忆召回 (Cross-Session Profile Recall)
    if writer:
        writer({
            "stage": "profile_recall",
            "message": "Recalling customer dietary preferences..."
        })

    profile_clause = "No special restrictions."
    if store is not None and effective_user_id != "GUEST":
        profile_namespace = ("users", effective_user_id, "dietary")
        profile_item = await store.aget(profile_namespace, "profile")
        if profile_item and profile_item.value:
            profile = UserDietaryProfile(**profile_item.value)
            profile_clause = profile.to_system_prompt_clause()
            logger.info(f"🧠 [Long-Term Memory] Recalled profile for user '{effective_user_id}': {profile_item.value}")

    # 2. 检索实时菜单与库存
    if writer:
        writer({
            "stage": "menu_scan",
            "message": "Checking live kitchen menu and inventory..."
        })

    menu_text = ""
    available_dishes = []
    try:
        async with AsyncSessionLocal() as session:
            available_dishes = await DishRepository.get_all_available(session)
            menu_items = [
                f"- {d.name}: Price=${d.price:.2f}, In-Stock={d.stock}, PrepTime={d.prep_time_minutes} mins"
                for d in available_dishes if d.stock > 0
            ]
            menu_text = "\n".join(menu_items)
    except Exception as e:
        logger.warning(f"⚠️ [DishAdvisor] Database session unavailable ({e}). Using standby offline menu.")
        menu_text = (
            "- Low-Cal Salmon Salad: Price=$42.00, In-Stock=8, PrepTime=10 mins\n"
            "- Sauteed Seasonal Greens: Price=$22.00, In-Stock=15, PrepTime=8 mins\n"
            "- Kung Pao Chicken: Price=$38.00, In-Stock=10, PrepTime=15 mins\n"
            "- Steamed Dumplings: Price=$28.00, In-Stock=20, PrepTime=12 mins"
        )

    # 3. 广播结构化菜品推荐卡片给前端
    if writer and available_dishes:
        in_stock_dishes = [d for d in available_dishes if d.stock > 0]
        if in_stock_dishes:
            writer({
                "type": "card",
                "card_type": "dish_recommendation",
                "items": [
                    {
                        "dish_id": d.id,
                        "name": d.name,
                        "price": float(d.price),
                        "prep_time": d.prep_time_minutes
                    }
                    for d in in_stock_dishes[:3]
                ]
            })
    llm = get_llm(temperature=0.2)
    system_prompt = (
        "You are the Sky Takeout Gourmet Advisor.\n"
        "=== LIVE KITCHEN MENU & INVENTORY ===\n"
        f"{menu_text}\n"
        "======================================\n\n"
        "=== CUSTOMER LIFETIME DIETARY PROFILE ===\n"
        f"{profile_clause}\n"
        "=========================================\n"
        "STRICT SAFETY & ALLERGY DIRECTIVES:\n"
        "1. ZERO TOLERANCE FOR ALLERGENS: If the customer has ANY allergy or restriction (such as peanuts, tree nuts, shellfish),\n"
        "   you MUST NEVER recommend any dish that typically, traditionally, or potentially contains that allergen!\n"
        "   For example, Kung Pao Chicken MUST NEVER be recommended to a peanut-allergic customer under any circumstances.\n"
        "   Do NOT offer caveats like 'please confirm with kitchen'—completely exclude hazardous dishes and ONLY recommend 100% safe options (e.g. Sauteed Greens, Salmon Salad, Steamed Dumplings)!\n"
        "2. ONLY recommend dishes that are currently IN-STOCK from the live menu above.\n"
        "3. State the exact dish name, price, and estimated prep time warmly in 2 concise sentences."
    )
    # ❌ 修改前：全量发送
    # response = await llm.ainvoke([SystemMessage(content=system_prompt)] + state["messages"])
    # ✅ 修改后：精简上下文发送
    optimized_prompt = prepare_trimmed_messages(
        system_prompt=system_prompt,
        raw_messages=state["messages"]
    )
    response = await llm.ainvoke(optimized_prompt)
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
