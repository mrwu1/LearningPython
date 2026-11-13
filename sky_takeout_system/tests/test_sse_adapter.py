import asyncio
from langchain_core.messages import AIMessage, AIMessageChunk
from app.core.streaming.adapter import LangGraphStreamAdapter
from app.core.streaming.protocol import SSEEventType, SSEEvent


async def test_stream_adapter_full_lifecycle():
    """Verifies that token, thought, progress, and updates are parsed properly while masking internal router."""
    print("\n[Case 1] Stream Adapter: Token, Thought & Progress Dispatch")
    adapter = LangGraphStreamAdapter(trace_id="test_trace_123")

    async def mock_stream():
        # 1. Supervisor decision (should be masked from user)
        yield "messages", (
            AIMessageChunk(content='{"next_worker": "dish_advisor"}'),
            {"langgraph_node": "supervisor"}
        )
        # 2. Specialist thought delta (DeepSeek-R1 style)
        yield "messages", (
            AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Evaluating customer dietary needs..."}),
            {"langgraph_node": "dish_advisor"}
        )
        # 3. Specialist text token delta
        yield "messages", (
            AIMessageChunk(content="Hello! "),
            {"langgraph_node": "dish_advisor"}
        )
        yield "messages", (
            AIMessageChunk(content="We have fresh Kung Pao Chicken!"),
            {"langgraph_node": "dish_advisor"}
        )
        # 4. Final state snapshot AIMessage (MUST NOT be yielded to avoid duplicate full text)
        yield "messages", (
            AIMessage(content="Hello! We have fresh Kung Pao Chicken!"),
            {"langgraph_node": "dish_advisor"}
        )
        # 5. Custom progress emitted by specialist via StreamWriter
        yield "custom", {
            "stage": "menu_scan",
            "message": "Checking live kitchen menu and inventory..."
        }
        # 6. Node completion update
        yield "updates", {
            "dish_advisor": {"messages": ["done"]}
        }

    events = [event async for event in adapter.transform(mock_stream())]

    # Verify event count and sequence
    assert len(events) == 5, f"Expected 5 events, got {len(events)}"

    # Event 0: Thought
    assert events[0].event == SSEEventType.THOUGHT
    assert events[0].data["node"] == "dish_advisor"
    assert events[0].data["delta"] == "Evaluating customer dietary needs..."
    print("  ✅ [PASS] Thought event correctly extracted from reasoning_content")

    # Event 1: Token chunk 1
    assert events[1].event == SSEEventType.TOKEN
    assert events[1].data["delta"] == "Hello! "
    print("  ✅ [PASS] Token delta correctly yielded")

    # Event 2: Token chunk 2
    assert events[2].event == SSEEventType.TOKEN
    assert events[2].data["delta"] == "We have fresh Kung Pao Chicken!"

    # Event 3: Custom progress
    assert events[3].event == SSEEventType.PROGRESS
    assert events[3].data["progress"]["stage"] == "menu_scan"
    print("  ✅ [PASS] Custom StreamWriter progress correctly dispatched")

    # Event 4: Node update
    assert events[4].event == SSEEventType.NODE_UPDATE
    assert events[4].data["nodes"] == ["dish_advisor"]
    assert events[4].data["trace_id"] == "test_trace_123"
    print("  ✅ [PASS] Superstep node update event correctly formatted")

    # Verify SSE dictionary serialization
    sse_dict = events[1].to_sse_dict()
    assert sse_dict["event"] == "token"
    assert '"delta": "Hello! "' in sse_dict["data"]
    print("  ✅ [PASS] SSE format serialization matches EventSource specifications")


async def test_stream_adapter_card_and_ping_events():
    """Verifies that structured UI cards and keep-alive ping events are handled correctly."""
    print("\n[Case 2] Stream Adapter: Card & Ping Protocol Verification")
    adapter = LangGraphStreamAdapter(trace_id="test_trace_cards")

    async def mock_stream_with_cards():
        # Specialist emits interactive UI card
        yield "custom", {
            "type": "card",
            "card_type": "dish_recommendation",
            "items": [
                {"dish_id": 1, "name": "Kung Pao Chicken", "price": 38.0}
            ]
        }

    events = [event async for event in adapter.transform(mock_stream_with_cards())]
    assert len(events) == 1
    assert events[0].event == SSEEventType.CARD
    assert events[0].data["card"]["card_type"] == "dish_recommendation"
    assert len(events[0].data["card"]["items"]) == 1
    print("  ✅ [PASS] Structured UI card event correctly categorized as SSEEventType.CARD")

    # Verify PING event serialization
    ping_event = SSEEvent(
        event=SSEEventType.PING,
        data={"ping": True, "trace_id": "test_trace_cards"}
    )
    ping_dict = ping_event.to_sse_dict()
    assert ping_dict["event"] == "ping"
    assert '"ping": true' in ping_dict["data"].lower()
    print("  ✅ [PASS] Keep-alive PING event correctly formatted")


async def main():
    print("=" * 60)
    print("🚀 [TEST SUITE] Enterprise SSE Stream Adapter Verification")
    print("=" * 60)
    await test_stream_adapter_full_lifecycle()
    await test_stream_adapter_card_and_ping_events()
    print("\n🎉 ALL STREAM ADAPTER TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
