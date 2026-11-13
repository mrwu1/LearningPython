import asyncio
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessageChunk
from app.core.streaming.adapter import LangGraphStreamAdapter
from app.core.streaming.protocol import SSEEventType
from app.schemas.takeout import TakeoutChatRequest
from app.services.agent.takeout_stream_svc import run_takeout_agent_stream


async def test_heartbeat_and_metrics_in_stream_service():
    """Verifies that the service emits PING on timeout and injects duration_ms into DONE."""
    print("\n[Case 1] Stream Service: Heartbeat Ping & Done Metrics Verification")

    # Mock Graph
    mock_graph = MagicMock()

    async def mock_slow_astream(*args, **kwargs):
        # 1. First event
        yield "messages", (AIMessageChunk(content="Hi"), {"langgraph_node": "dish_advisor"})
        # 2. Simulate delay longer than heartbeat interval (0.1s heartbeat interval, sleep 0.25s)
        await asyncio.sleep(0.25)
        # 3. Next event
        yield "messages", (AIMessageChunk(content="!"), {"langgraph_node": "dish_advisor"})

    mock_graph.astream = mock_slow_astream

    # Mock snapshot without interrupt
    mock_snapshot = MagicMock()
    mock_snapshot.tasks = []
    mock_graph.aget_state = AsyncMock(return_value=mock_snapshot)

    # Mock Request
    mock_request = MagicMock()
    mock_request.is_disconnected = AsyncMock(return_value=False)

    payload = TakeoutChatRequest(
        query="Recommend food",
        session_id="test_sess_heartbeat"
    )

    adapter = LangGraphStreamAdapter(trace_id="trace_hb_test")

    # Set heartbeat_interval to 0.1s so test finishes in 0.3s
    events = []
    async for event in run_takeout_agent_stream(
        graph=mock_graph,
        payload=payload,
        trace_id="trace_hb_test",
        adapter=adapter,
        request=mock_request,
        heartbeat_interval=0.1
    ):
        events.append(event)

    event_types = [e.event for e in events]
    print(f"  Received event sequence: {[e.value for e in event_types]}")

    # Assertions
    assert SSEEventType.TOKEN in event_types
    assert SSEEventType.PING in event_types, "Expected PING heartbeat due to simulated 0.25s delay!"
    assert SSEEventType.DONE in event_types

    # Verify duration_ms in DONE metrics
    done_event = [e for e in events if e.event == SSEEventType.DONE][0]
    assert "metrics" in done_event.data
    assert "duration_ms" in done_event.data["metrics"]
    assert done_event.data["metrics"]["duration_ms"] >= 200
    print(f"  ✅ [PASS] Heartbeat emitted and duration_ms recorded: {done_event.data['metrics']['duration_ms']}ms")


async def main():
    print("=" * 60)
    print("🚀 [TEST SUITE] Enterprise SSE Service Lifecycle Verification")
    print("=" * 60)
    await test_heartbeat_and_metrics_in_stream_service()
    print("\n🎉 ALL STREAM SERVICE TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
