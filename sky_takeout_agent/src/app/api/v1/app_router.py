from fastapi import APIRouter

from app.core.config import settings
from loguru import logger

api_router = APIRouter()

@api_router.get("/healthz",summary="health check")
def check_health()->dict:
    logger.info("正在执行健康检查探针逻辑...")
    return {
        "status": "ok",
        "app_name": settings.APP_NAME,
        "env": settings.ENV_MODE,
        "db_target": f"{settings.DB_USER}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}",
        # 注意：SecretStr 取出真实密钥必须调 .get_secret_value()
        "key_masked": f"{settings.OPENAI_API_KEY.get_secret_value()[:6]}******"
    }