from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse

from app.api.deps import get_db_session, get_current_user
from app.core.config import settings
from app.core.logging import trace_id_ctx
from app.core.rate_limiter import RedisSlidingWindowLimiter
from app.core.streaming.adapter import LangGraphStreamAdapter
from app.core.streaming.session_guard import guard_stream_session
from app.models import User
from app.schemas.takeout import TakeoutChatRequest
from app.services.agent.takeout_stream_svc import verify_order_access, run_takeout_agent_stream

router = APIRouter(prefix="/takeout", tags=["Takeout Agent Interactions"])

# Module-level rate limiter for authenticated chat interactions
chat_user_limiter = RedisSlidingWindowLimiter(
    key_prefix="rate_limit:chat:user",
    max_requests=settings.RATE_LIMIT_USER_MAX_REQUESTS,
    window_seconds=settings.RATE_LIMIT_USER_WINDOW_WINDOW_SECONDS if hasattr(settings, "RATE_LIMIT_USER_WINDOW_WINDOW_SECONDS") else settings.RATE_LIMIT_USER_WINDOW_SECONDS,
)


@router.post("/chat")
async def chat_stream_endpoint(
    payload: TakeoutChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),       # 👈 Requires valid JWT token
    session: AsyncSession = Depends(get_db_session)        # 👈 Database session for ownership verification
):
    """
    Decoupled Customer SSE Chat Endpoint:
    Guards ingress via sliding-window rate limiting & anti-IDOR checks,
    acquires distributed session lock via session guard,
    and streams multi-channel agent events (token, thought, progress, interrupt).
    """
    # 1. Layer 0 Defense: Sliding-window rate limiting and anti-IDOR checks
    await chat_user_limiter.check_and_record(current_user.user_identifier)
    await verify_order_access(session, payload, current_user)

    # 2. Extract tracing context and LangGraph singleton
    trace_id = trace_id_ctx.get()
    graph = request.app.state.graph

    # 3. Delegate to streaming pipeline
    async def sse_stream():
        # 动作 1：进房间，把门反锁 (抢 Redis 锁)
        async with guard_stream_session(payload.session_id):
            # 动作 2：把同声传译翻译机搬进房间 - 得到控制权 - 开始执行代码 ‼️ ‼️ ‼️ ‼️ ‼️ ‼️ ‼️ ‼️
            adapter = LangGraphStreamAdapter(trace_id=trace_id)

            # 动作 3：站在流水线终点，等下一包数据传过来 -  # 从这条传送带上，一个一个取走数据包：
            async for sse_event in run_takeout_agent_stream(
                graph=graph,
                payload=payload,
                trace_id=trace_id,
                adapter=adapter,
                request=request
            ):
                # 动作 4：把拿到的一包数据，顺着网线直接“吐”给前端
                yield sse_event.to_sse_dict()

    # 👈 你把这个“接力队”交给了 FastAPI 的 EventSourceResponse
    # EventSourceResponse 对你的 sse_stream() 说：“给我来一个数据包！”
    # 他左手拿着一把安全锁（guard_stream_session），右手接通后方的净水器（run_takeout_agent_stream）；
    # 每产生一个 Token，他就用勺子盛给前方的客人（yield）；客人喝完了或者走了，他随手把门锁锁好离开。
    return EventSourceResponse(
        sse_stream(),  # 就是一个“水管工”：
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # 禁止 Nginx 缓冲长连接数据块
        }
    )
