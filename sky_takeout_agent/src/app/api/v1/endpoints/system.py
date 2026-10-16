from fastapi import APIRouter
from loguru import logger
from app.core.config import settings
from app.core.redis_client import redis_client

router = APIRouter(tags=["系统探针"])

@router.get("/healthz", summary="服务基础健康检查")
def check_health() -> dict:
    logger.info("正在执行健康检查探针逻辑...")
    return {
        "status": "ok",
        "app_name": settings.APP_NAME,
        "env": settings.ENV_MODE,
        "db_target": f"{settings.DB_USER}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}",
        "key_masked": f"{settings.OPENAI_API_KEY.get_secret_value()[:6]}******"
    }

@router.get("/health_redis", summary="Redis 连接健康检查")
async def check_redis_connections() -> bool:
    """health check: test the connection status for redis"""
    try:
        await redis_client.ping()
        logger.info("✅ Redis 异步连接池就绪！")
        return True
    except Exception as e:
        logger.error(f"❌ Redis 连接失败: {e}")
        return False
