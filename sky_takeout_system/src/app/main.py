from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from app.api.middlewares import TraceIDMiddleware
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import async_engine
from app.core.redis import close_redis_client
from app.services.agent.graph_factory import init_production_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Enterprise Application Lifespan:
    1. Initializes PostgreSQL connection pool and compiles LangGraph singleton engine.
    2. Guarantees clean resource release (Redis pool, MySQL pool) on shutdown.
    """
    logger.info("🚀 [Lifespan Startup] Booting Sky Takeout Enterprise Microservice...")
    
    # 编译并托管智能体单例图
    async with init_production_graph() as compiled_graph:
        app.state.graph = compiled_graph
        logger.info("🎯 [Lifespan Startup] LangGraph engine mounted to app.state.graph successfully.")
        yield

    logger.info("🛑 [Lifespan Shutdown] Releasing system infrastructure pools...")
    await close_redis_client()
    await async_engine.dispose()
    logger.info("✅ [Lifespan Shutdown] All pools disposed cleanly.")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Sky Takeout Enterprise Multi-Agent System (Production Grade)",
    lifespan=lifespan
)

# 1. 注册生产链路追踪中间件
app.add_middleware(TraceIDMiddleware)

# 2. 注册标准 CORS 跨域防护中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. 挂载 API V1 统一路由网关
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root metadata probe."""
    return {
        "service": settings.APP_NAME,
        "environment": settings.ENV_MODE,
        "status": "ONLINE"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=settings.APP_PORT, reload=True)
