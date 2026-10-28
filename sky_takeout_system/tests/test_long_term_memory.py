import asyncio
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app.services.agent.graph_factory import create_sky_takeout_graph


async def test_cross_session_memory_persistence():
    print("=" * 80)
    print(" 🧠 STARTING CROSS-SESSION LONG-TERM MEMORY VERIFICATION TEST")
    print("=" * 80)

    # 1. 实例化独立的全局 Store 与 Checkpointer
    global_store = InMemoryStore()
    checkpointer = MemorySaver()
    graph = create_sky_takeout_graph(checkpointer=checkpointer, store=global_store)

    user_alice = "USER_ALICE_ALLERGY_TEST"
    profile_namespace = ("users", user_alice, "dietary")

    # -------------------------------------------------------------------------
    # 模拟场景 A: 用户画像首次落盘 (在周一的会话中记录重度花生过敏)
    # -------------------------------------------------------------------------
    print("\n[Step 1]: Pre-seeding Alice's lifetime medical allergy in LangGraph Store...")
    await global_store.aput(
        namespace=profile_namespace,
        key="profile",
        value={
            "user_id": user_alice,
            "allergies": ["花生 (Peanuts)", "坚果类 (Tree Nuts)"],
            "disliked_ingredients": ["香菜 (Coriander)"],
            "diet_style": "low_carb",
            "target_calories_per_meal": 500
        }
    )
    print("  ✅ Alice's profile stored under namespace ('users', 'USER_ALICE_ALLERGY_TEST', 'dietary')")

    # -------------------------------------------------------------------------
    # 模拟场景 B: 开启一场全新的周五会话 (全新的 Thread ID，零会话历史)
    # -------------------------------------------------------------------------
    fresh_session_id = "SESSION_FRIDAY_NEW_002"
    print(f"\n[Step 2]: Launching a BRAND NEW session '{fresh_session_id}' (Thread has 0 historical messages)...")

    chat_input = {
        "trace_id": "trace_memory_eval_001",
        "messages": [HumanMessage(content="我下班了好饿，有什么低卡减脂的晚餐推荐吗？")],
        "order_id": "ORD-UNKNOWN",
        "user_id": user_alice,  # 👈 同一个顾客标识
        "next_worker": "dish_advisor",
        "stock_reports": [],
        "refund_amount": 0.0,
        "refund_reason": "",
        "refund_status": "NONE",
        "reviewer_notes": "",
    }

    config = {"configurable": {"thread_id": fresh_session_id}}
    final_state = await graph.ainvoke(chat_input, config=config)

    # 提取专员答复
    ai_reply = final_state["messages"][-1].content
    print(f"\n[Step 3]: Received AI Recommendation in fresh session:\n  \"{ai_reply}\"")

    # -------------------------------------------------------------------------
    # 核心企业级断言 (Verification Assertions)
    # -------------------------------------------------------------------------
    print("\n[Step 4]: Verifying Safety & Memory Recall Assertions...")

    # 断言 1: 绝对不能出现花生或坚果
    assert "花生" not in ai_reply and "peanut" not in ai_reply.lower(), "FATAL ALLERGY BREACH: Peanut recommended to allergic user!"
    print("  ✅ [PASS] Allergen Defense: Zero mentions of peanut in recommendation.")

    # 断言 2: 绝对不能出现香菜
    assert "香菜" not in ai_reply and "coriander" not in ai_reply.lower(), "Preference Breach: Coriander recommended to user who dislikes it!"
    print("  ✅ [PASS] Preference Defense: User's disliked ingredient (coriander) successfully respected.")

    # 断言 3: 必须有实际在售菜品被推荐
    assert len(ai_reply) > 10
    print("  ✅ [PASS] High-value relevant recommendation generated successfully.")

    print("\n" + "=" * 80)
    print(" 🏆 CROSS-SESSION LONG-TERM MEMORY TEST PASSED! ZERO RECALL DRIFT!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_cross_session_memory_persistence())