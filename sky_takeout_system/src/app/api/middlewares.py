import time
import uuid
from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logging import trace_id_ctx


class TraceIDMiddleware(BaseHTTPMiddleware):
    """
    Enterprise Observability Middleware:
    Extracts or generates an X-Request-ID, binds it to the async contextvars,
    monitors microsecond request latency, and appends the TraceID to response headers.
    """
    async def dispatch(self, request: Request, call_next):
        # 1. 优先读取网关或客户端传来的 TraceID，若无则自动生成短 UUID
        trace_id = request.headers.get("X-Request-ID", f"TR-{uuid.uuid4().hex[:10].upper()}")
        token = trace_id_ctx.set(trace_id)

        start_time = time.perf_counter()
        logger.info(f"🌐 [HTTP Start] {request.method} {request.url.path}")

        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"🏁 [HTTP End] {request.method} {request.url.path} "
                f"- Status: {response.status_code} - Latency: {elapsed_ms:.2f}ms"
            )
            response.headers["X-Request-ID"] = trace_id
            return response
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"💥 [HTTP Error] {request.method} {request.url.path} "
                f"- Error: {e} - Latency: {elapsed_ms:.2f}ms"
            )
            raise
        finally:
            # 保证协程退出时重置 contextvars，杜绝内存泄漏与上下文污染
            trace_id_ctx.reset(token)
