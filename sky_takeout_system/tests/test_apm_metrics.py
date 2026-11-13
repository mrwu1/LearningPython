import asyncio
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessage, AIMessageChunk
from prometheus_client import generate_latest

from app.core.streaming.adapter import LangGraphStreamAdapter
from app.core.streaming.protocol import SSEEventType
from app.core.telemetry.cost_tracker import TokenCostCalculator, TokenUsageReport
from app.core.telemetry.metrics import (
    AGENT_REQUESTS_TOTAL,
    AGENT_TTFT_SECONDS,
    AGENT_DURATION_SECONDS,
    AGENT_TOKENS_TOTAL,
    AGENT_COST_USD_TOTAL,
    AGENT_ACTIVE_SESSIONS,
)
from app.schemas.takeout import TakeoutChatRequest
from app.services.agent.takeout_stream_svc import run_takeout_agent_stream


def test_token_cost_calculator():
    """Verifies that token cost is calculated with micro-cent accuracy for DeepSeek."""
    print("\n[Case 1] Token Cost Calculator: Pricing Accuracy")

    # 1,000,000 prompt tokens ($0.14) + 1,000,000 completion tokens ($0.28)
    report = TokenCostCalculator.calculate(
        model_name="deepseek-chat",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000
    )
    assert report.total_tokens == 2_000_000
    assert abs(report.cost_usd - 0.42) < 1e-6
    print(f"  ✅ [PASS] 1M prompt + 1M completion cost: ${report.cost_usd:.4f} USD")

    # Typical turn: 500 prompt tokens, 100 completion tokens
    turn_report = TokenCostCalculator.calculate(
        model_name="deepseek-chat",
        prompt_tokens=500,
        completion_tokens=100
    )
    # (500 / 1e6)*0.14 + (100 / 1e6)*0.28 = 0.00007 + 0.000028 = 0.000098 USD
    expected_cost = 0.000098
    assert abs(turn_report.cost_usd - expected_cost) < 1e-6
    d = turn_report.to_dict()
    assert d["cost_usd"] == round(expected_cost, 6)
    print(f"  ✅ [PASS] Typical turn (500+100 tokens) cost: ${d['cost_usd']:.6f} USD")


async def test_apm_telemetry_in_stream_service():
    """Verifies that TTFT, duration, token usage, and Prometheus metrics are recorded in streaming."""
    print("\n[Case 2] End-to-End Stream APM Telemetry & Prometheus Metrics")

    mock_graph = MagicMock()

    async def mock_stream(*args, **kwargs):
        # Simulate initial latency before first token (TTFT)
        await asyncio.sleep(0.08)
        yield "messages", (AIMessageChunk(content="Delicious"), {"langgraph_node": "dish_advisor"})
        await asyncio.sleep(0.05)
        yield "messages", (AIMessageChunk(content=" dumplings!"), {"langgraph_node": "dish_advisor"})

    mock_graph.astream = mock_stream

    # Snapshot with AIMessage containing token usage metadata
    mock_snapshot = MagicMock()
    mock_snapshot.tasks = []
    mock_snapshot.values = {
        "messages": [
            AIMessage(
                content="Delicious dumplings!",
                usage_metadata={"input_tokens": 350, "output_tokens": 80, "total_tokens": 430}
            )
        ]
    }
    mock_graph.aget_state = AsyncMock(return_value=mock_snapshot)

    mock_request = MagicMock()
    mock_request.is_disconnected = AsyncMock(return_value=False)

    payload = TakeoutChatRequest(
        query="What is good?",
        session_id="apm_test_session"
    )

    adapter = LangGraphStreamAdapter(trace_id="trace_apm_001")

    # Initial cost counter value
    cost_before = AGENT_COST_USD_TOTAL._value.get()

    events = []
    async for event in run_takeout_agent_stream(
        graph=mock_graph,
        payload=payload,
        trace_id="trace_apm_001",
        adapter=adapter,
        request=mock_request,
        heartbeat_interval=5.0
    ):
        events.append(event)

    # Verify event stream
    assert len(events) == 3  # token 1, token 2, done
    done_event = events[-1]
    assert done_event.event == SSEEventType.DONE

    data = done_event.data
    assert data["status"] == "COMPLETED"

    # Verify TTFT & Duration
    metrics_info = data["metrics"]
    assert metrics_info["ttft_ms"] >= 70, f"Expected TTFT >= 70ms, got {metrics_info['ttft_ms']}ms"
    assert metrics_info["duration_ms"] >= 120, f"Expected Duration >= 120ms, got {metrics_info['duration_ms']}ms"
    print(f"  ✅ [PASS] TTFT measured: {metrics_info['ttft_ms']}ms | Duration: {metrics_info['duration_ms']}ms")

    # Verify Token Usage & Cost
    usage_info = data["usage"]
    assert usage_info["prompt_tokens"] == 350
    assert usage_info["completion_tokens"] == 80
    assert usage_info["total_tokens"] == 430
    assert usage_info["cost_usd"] > 0
    print(f"  ✅ [PASS] Usage reported: {usage_info['total_tokens']} tokens | Cost: ${usage_info['cost_usd']:.6f} USD")

    # Verify Prometheus cost counter incremented
    cost_after = AGENT_COST_USD_TOTAL._value.get()
    assert cost_after > cost_before
    print(f"  ✅ [PASS] Prometheus counter AGENT_COST_USD_TOTAL incremented successfully")

    # Verify Prometheus scraping endpoint output
    metrics_output = generate_latest().decode("utf-8")
    assert "agent_requests_total" in metrics_output
    assert "agent_ttft_seconds" in metrics_output
    assert "agent_duration_seconds" in metrics_output
    assert "agent_tokens_total" in metrics_output
    assert "agent_cost_usd_total" in metrics_output
    print("  ✅ [PASS] Prometheus generate_latest() contains all enterprise agent metrics")


async def main():
    print("=" * 60)
    print("🚀 [TEST SUITE] Enterprise APM Telemetry & Metrics Verification")
    print("=" * 60)
    test_token_cost_calculator()
    await test_apm_telemetry_in_stream_service()
    print("\n🎉 ALL APM TELEMETRY TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
