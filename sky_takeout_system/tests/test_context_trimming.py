import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.services.agent.context_manager import prepare_trimmed_messages


def test_enterprise_context_trimming():
    print("=" * 70)
    print(" ✂️ STARTING ENTERPRISE CONTEXT TRIMMING VERIFICATION TEST")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # Case 1: 简短对话 (低于阈值时不触发截断，100% 原样保留)
    # -------------------------------------------------------------------------
    print("\n[Case 1]: Testing short conversation below limit (3 messages)...")
    short_history = [
        HumanMessage(content="Recommend a low-calorie lunch."),
        AIMessage(content="I recommend the fresh salmon bowl.", name="dish_advisor"),
        HumanMessage(content="What about the prep time?"),
    ]
    short_res = prepare_trimmed_messages(
        system_prompt="You are Gourmet Advisor.",
        raw_messages=short_history,
        max_messages=6,
    )
    print(f"  Short dialogue total count: {len(short_res)} (1 System + 3 Dialogue)")
    assert len(short_res) == 4
    assert isinstance(short_res[0], SystemMessage)
    print("  ✅ [PASS] Short conversation preserved without unwanted pruning!")

    # -------------------------------------------------------------------------
    # Case 2: 14 轮超长历史会话 (测试滑动窗口精准切片)
    # -------------------------------------------------------------------------
    print("\n[Case 2]: Simulating long 14-turn conversation (Testing sliding window)...")
    long_history = []
    for i in range(1, 8):
        long_history.append(HumanMessage(content=f"User question #{i}"))
        long_history.append(AIMessage(content=f"Agent response #{i}", name="specialist"))

    print(f"  Original Message Count: {len(long_history)} messages")

    trimmed_res = prepare_trimmed_messages(
        system_prompt="You are Takeout Supervisor.",
        raw_messages=long_history,
        max_messages=6,
    )

    print(f"  Trimmed Output Count: {len(trimmed_res)} (1 System + 6 Dialogue)")

    # 核心断言 1: 必须为 1 条置顶系统提示词 + 6 条对话
    assert len(trimmed_res) == 7

    # 核心断言 2: index 0 必须是权威 SystemMessage
    assert isinstance(trimmed_res[0], SystemMessage)
    print(f"  ✅ [Check 1] System prompt pinned at index 0: '{trimmed_res[0].content}'")

    # 核心断言 3: 非系统消息的第一句必须是 HumanMessage
    assert isinstance(trimmed_res[1], HumanMessage)
    print(f"  ✅ [Check 2] First dialogue turn begins with HumanMessage: '{trimmed_res[1].content}'")

    # 核心断言 4: 保留的是最新的轮次 (从 User question #5 到 Agent response #7)
    assert trimmed_res[1].content == "User question #5"
    assert trimmed_res[-1].content == "Agent response #7"
    print(f"  ✅ [Check 3] Sliding window accurately captured latest turns: '{trimmed_res[1].content}' ->'{trimmed_res[-1].content}'")

    # -------------------------------------------------------------------------
    # Case 3: Token 节省率度量
    # -------------------------------------------------------------------------
    print("\n[Case 3]: Measuring Token Reduction...")
    original_chars = sum(len(m.content) for m in long_history)
    trimmed_chars = sum(len(m.content) for m in trimmed_res[1:])
    savings = (1 - trimmed_chars / original_chars) * 100
    print(f"  Original Dialogue Chars: {original_chars}")
    print(f"  Trimmed Dialogue Chars: {trimmed_chars}")
    print(f"  📊 Token / Character Savings Ratio: {savings:.1f}%")
    assert savings >= 50.0
    print("  ✅ [PASS] Confirmed > 50% token cost reduction!")

    print("\n" + "=" * 70)
    print(" 🏆 ALL CONTEXT TRIMMING TEST CASES PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
        test_enterprise_context_trimming()