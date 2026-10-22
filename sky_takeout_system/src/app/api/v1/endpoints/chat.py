import json
from fastapi import APIRouter, Request, HTTPException, status, Depends
from langchain_core.messages import HumanMessage
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse

from app.api.deps import get_db_session, get_current_user
from app.core.config import settings
from app.core.logging import trace_id_ctx
from app.core.rate_limiter import RedisSlidingWindowLimiter
from app.core.redis import DistributedSessionLock
from app.models import User
from app.repositories.order_repo import OrderRepository
from app.schemas.takeout import TakeoutChatRequest

router = APIRouter(prefix="/takeout", tags=["Takeout Agent Interactions"])

# Module-level rate limiter for authenticated chat interactions
chat_user_limiter = RedisSlidingWindowLimiter(
    key_prefix="rate_limit:chat:user",
    max_requests=settings.RATE_LIMIT_USER_MAX_REQUESTS,
    window_seconds=settings.RATE_LIMIT_USER_WINDOW_SECONDS,
)


@router.post("/chat")
async def chat_stream_endpoint(
        payload: TakeoutChatRequest,
        request: Request,
        current_user: User = Depends(get_current_user),       # 👈 Requires valid JWT token
        session: AsyncSession = Depends(get_db_session)  # 👈 Database session for ownership verification
):
    """
    Customer SSE Chat Endpoint:
    Guarded by Redis Distributed Session Lock, streams live node progress over SSE,
    and dynamically detects interrupt() breakpoints for human-in-the-loop review.
    """
    effective_user_id = current_user.user_identifier

    # 0. Global Abuse Prevention & Sliding Window Rate Limiting (Layer 0 Defense)
    await chat_user_limiter.check_and_record(effective_user_id)

    # 1. Anti-IDOR & Financial Tampering Defense
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
    # end auth
    thread_id = payload.session_id
    lock = DistributedSessionLock(thread_id=thread_id, lease_seconds=45)

    # 1. 获取 Redis 分布式会话锁 (多 Pod 集群防并发脏写)
    if not await lock.acquire():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Session '{thread_id}' is currently busy. Please wait for the previous turn to complete."
        )

    graph = request.app.state.graph
    current_trace_id = trace_id_ctx.get()
    config = {"configurable": {"thread_id": thread_id}}

    initial_input = {
        "trace_id": current_trace_id,
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

    async def sse_generator():
        try:
            logger.info(f"⚡ [SSE Stream Start] Session: {thread_id} | TraceID: {current_trace_id}")
            async for mode, event in graph.astream(initial_input, stream_mode=["updates"], config=config):
                # 客户端断连检测
                if await request.is_disconnected():
                    logger.warning(f"Client disconnected for session {thread_id}. Aborting stream.")
                    break

                # 推送superstep node 完成事件
                active_nodes = list(event.keys())
                yield {
                    "event": "node_update",
                    "data": json.dumps({"nodes": active_nodes, "trace_id": current_trace_id}, ensure_ascii=False)
                }

            # 检查图在持久化快照中是否处于动态断点挂起态
            snapshot = await graph.aget_state(config)
            if snapshot.tasks and snapshot.tasks[0].interrupts:
                alert_info = snapshot.tasks[0].interrupts[0].value
                logger.info(f"🚨 [Interrupt Triggered] Session {thread_id} paused at human review: {alert_info}")
                yield {
                    "event": "human_approval_required",
                    "data": json.dumps({
                        "session_id": thread_id,
                        "trace_id": current_trace_id,
                        "alert": alert_info
                    }, ensure_ascii=False)
                }
            else:
                yield {
                    "event": "done",
                    "data": "[DONE]"
                }
        except Exception as e:
            logger.error(f"💥 [SSE Stream Error] Session {thread_id}: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e), "trace_id": current_trace_id}, ensure_ascii=False)
            }
        finally:
            # 无论流正常结束、中断挂起还是客户端断连，必须安全释放分布式锁！
            await lock.release()
            logger.info(f"🏁 [SSE Stream Closed] Distributed lock released for session {thread_id}")

    return EventSourceResponse(
        sse_generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # 禁止 Nginx 缓冲长连接数据块
        }
    )
