from typing import Optional
import redis.asyncio as aioredis
from loguru import logger

from app.core.config import settings

# Module-level singleton Redis client
_redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """
    Thread-safe / Loop-safe Redis Client Provider:
    Direct parameter instantiation prevents password URL-encoding bugs with '@' symbols.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            db=settings.REDIS_DB,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
            socket_timeout=10.0,
            socket_connect_timeout=5.0
        )
    return _redis_client


async def close_redis_client() -> None:
    """Closes Redis connection pool cleanly during application shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("🛑 [Redis Pool] Connection pool closed successfully.")