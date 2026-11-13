import asyncio
import time
from typing import AsyncIterator
from fastapi import HTTPException, status, Request
from langchain_core.messages import HumanMessage
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.streaming.adapter import LangGraphStreamAdapter
from app.core.streaming.protocol import SSEEvent, SSEEventType
from app.core.telemetry import (
    TokenCostCalculator,
    AGENT_REQUESTS_TOTAL,
    AGENT_TTFT_SECONDS,
    AGENT_DURATION_SECONDS,
    AGENT_TOKENS_TOTAL,
    AGENT_COST_USD_TOTAL,
    AGENT_ACTIVE_SESSIONS,
)
from app.models import User
from app.repositories.order_repo import OrderRepository
from app.schemas.takeout import TakeoutChatRequest


async def verify_order_access(
    session: AsyncSession,
    payload: TakeoutChatRequest,
    current_user: User
) -> None:
    """
    Anti-IDOR & Financial Safeguard Validation.
    Ensures customer only accesses their own order and refund amount does not exceed payment.
    """
    effective_user_id = current_user.user_identifier
    if payload.order_id and payload.order_id not in ["", "UNKNOWN"]:
        order = await OrderRepository.get_by_order_number(session, payload.order_id)
        if order:
            # Customers are strictly restricted to their own orders (Store Managers can inspect any order)
            if current_user.role != "ROLE_STORE_MANAGER" and order.user_id != effective_user_id:
                logger.warning(
                    f"🚨 [Security Alert] User {effective_user_id} attempted unauthorized access "
                    f"to order {payload.order_id} owned by {order.user_id}!"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: Order '{payload.order_id}' does not belong to your account."
                )

            # Financial Safeguard: Refund request cannot exceed actual order payment
            if payload.refund_amount and payload.refund_amount > float(order.total_amount):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid refund amount: Requested ${payload.refund_amount:.2f} "
                           f"exceeds order total paid amount of ${float(order.total_amount):.2f}."
                )


async def run_takeout_agent_stream(
    graph,
    payload: TakeoutChatRequest,
    trace_id: str,
    adapter: LangGraphStreamAdapter,
    request: Request,
    heartbeat_interval: float = 15.0
) -> AsyncIterator[SSEEvent]:
    """
    Coordinates graph streaming with active heartbeat keep-alive,
    TTFT latency measurement, token usage tracking, and Prometheus metrics.
    """
    thread_id = payload.session_id
    config = {"configurable": {"thread_id": thread_id}}

    initial_input = {
        "trace_id": trace_id,
        "messages": [HumanMessage(content=payload.query)],
        "order_id": payload.order_id,
        "user_id": payload.user_id,
        "next_worker": "dish_advisor",
        "stock_reports": [],
        "refund_amount": payload.refund_amount,
        "refund_reason": payload.refund_reason,
        "refund_status": "NONE",
        "reviewer_notes": ""
    }

    AGENT_ACTIVE_SESSIONS.inc()
    start_time = time.time()
    first_token_time = None
    ttft_ms = 0
    fetch_task = None

    try:
        logger.info(f"⚡ [SSE Stream Start] Session: {thread_id} | TraceID: {trace_id}")
        raw_stream = graph.astream(
            initial_input,
            stream_mode=["messages", "custom", "updates"],
            config=config
        )
        stream_iter = adapter.transform(raw_stream).__aiter__()

        # Persistent task pattern to ensure wait_for timeout does not cancel the generator
        fetch_task = asyncio.create_task(stream_iter.__anext__())

        while True:
            # Client disconnection check
            if await request.is_disconnected():
                logger.warning(f"🛑 [Client Disconnect] Session {thread_id} disconnected by user. Aborting.")
                break

            try:
                # Shield fetch_task so a heartbeat timeout only cancels the shield, not the generator
                sse_event = await asyncio.wait_for(asyncio.shield(fetch_task), timeout=heartbeat_interval)

                # Capture Time-To-First-Token (TTFT) on the very first token chunk
                if sse_event.event == SSEEventType.TOKEN and first_token_time is None:
                    first_token_time = time.time()
                    ttft_seconds = first_token_time - start_time
                    ttft_ms = int(ttft_seconds * 1000)
                    AGENT_TTFT_SECONDS.observe(ttft_seconds)

                yield sse_event
                # Advance to next event
                fetch_task = asyncio.create_task(stream_iter.__anext__())
            except asyncio.TimeoutError:
                # Heartbeat packet to prevent Nginx/ALB 504 timeout during long thinking/tool calls
                logger.debug(f"💓 [SSE Keep-Alive] Sending heartbeat ping to session {thread_id}")
                yield SSEEvent(
                    event=SSEEventType.PING,
                    data={"ping": True, "timestamp": int(time.time()), "trace_id": trace_id}
                )
            except StopAsyncIteration:
                # Generator finished normally
                break

        # Record total stream duration
        duration_seconds = time.time() - start_time
        duration_ms = int(duration_seconds * 1000)
        AGENT_DURATION_SECONDS.observe(duration_seconds)

        # Inspect persistent snapshot for state & usage
        snapshot = await graph.aget_state(config)

        # Extract and accumulate token usage across all messages in snapshot
        prompt_tokens = 0
        completion_tokens = 0
        if snapshot.values and "messages" in snapshot.values:
            for msg in snapshot.values["messages"]:
                if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                    prompt_tokens += msg.usage_metadata.get("input_tokens", 0)
                    completion_tokens += msg.usage_metadata.get("output_tokens", 0)
                elif hasattr(msg, "response_metadata") and "token_usage" in msg.response_metadata:
                    tu = msg.response_metadata["token_usage"]
                    prompt_tokens += tu.get("prompt_tokens", 0)
                    completion_tokens += tu.get("completion_tokens", 0)

        usage_report = TokenCostCalculator.calculate(
            model_name="deepseek-chat",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )

        # Record Prometheus token & cost counters
        AGENT_TOKENS_TOTAL.labels(model="deepseek-chat", type="prompt").inc(usage_report.prompt_tokens)
        AGENT_TOKENS_TOTAL.labels(model="deepseek-chat", type="completion").inc(usage_report.completion_tokens)
        AGENT_COST_USD_TOTAL.inc(usage_report.cost_usd)

        # Handle dynamic human-in-the-loop interrupts vs normal completion
        if snapshot.tasks and snapshot.tasks[0].interrupts:
            alert_info = snapshot.tasks[0].interrupts[0].value
            logger.info(f"🚨 [Interrupt Triggered] Session {thread_id} paused at human review: {alert_info}")
            AGENT_REQUESTS_TOTAL.labels(status="interrupt").inc()
            yield SSEEvent(
                event=SSEEventType.INTERRUPT,
                data={
                    "session_id": thread_id,
                    "trace_id": trace_id,
                    "alert": alert_info
                }
            )
        else:
            AGENT_REQUESTS_TOTAL.labels(status="success").inc()
            yield SSEEvent(
                event=SSEEventType.DONE,
                data={
                    "status": "COMPLETED",
                    "session_id": thread_id,
                    "trace_id": trace_id,
                    "usage": usage_report.to_dict(),
                    "metrics": {
                        "ttft_ms": ttft_ms,
                        "duration_ms": duration_ms
                    }
                }
            )

    except asyncio.CancelledError:
        logger.warning(f"⏹️ [Stream Cancelled] Task was cancelled for session {thread_id}")
        AGENT_REQUESTS_TOTAL.labels(status="cancelled").inc()
        raise
    except Exception as e:
        logger.error(f"💥 [SSE Stream Error] Session {thread_id}: {e}")
        AGENT_REQUESTS_TOTAL.labels(status="error").inc()
        yield SSEEvent(
            event=SSEEventType.ERROR,
            data={"error": str(e), "trace_id": trace_id}
        )
    finally:
        AGENT_ACTIVE_SESSIONS.dec()
        if fetch_task and not fetch_task.done():
            fetch_task.cancel()
