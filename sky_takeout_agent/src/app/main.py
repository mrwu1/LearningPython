import time
import uuid

from fastapi import FastAPI, Request
from loguru import logger

from app.api.v1.api import api_router
from app.core.logging import trace_id_ctx


app = FastAPI(title="sky takeout Agent",version="1.0")

# 1.CONFIG -全局请求拦截中间件：给每个进入系统的请求打上唯一 TraceID 并监控耗时
@app.middleware("http")
async def trace_id_middleware(request:Request,call_next):
    # 1. 优先读取前端/网关传来的 X-Request-ID，若无则自动生成短 UUID
    trace_id = request.headers.get("X-Request-ID",str(uuid.uuid4())[:8])
    token = trace_id_ctx.set(trace_id)

    start_time = time.perf_counter()
    logger.info(f"🌐 请求开始: {request.method} {request.url.path}")

    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter()-start_time)*1000 # s
        logger.info(f"🏁 请求结束: {request.method} {request.url.path} - 状态: {response.status_code} - 耗时:{elapsed_ms: .2f}ms")

        # 把 TraceID 回传给前端响应头
        response.headers["X-Request-ID"] = trace_id
        return response
    finally:
        #reset context
        trace_id_ctx.reset(token)

# 2. ADD ROUTER:
app.include_router(api_router,prefix="/api/v1")

# 全站所有接口默认上锁 ✅
#  app = FastAPI(dependencies=[Depends(get_current_user)])

# 对标 Spring：
# http.authorizeRequests()
#   .anyRequest().authenticated(); // 全站默认拦截

if __name__=="__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=9999, reload=True)