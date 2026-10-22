import uuid
from typing import Optional
import redis.asyncio as aioredis
from loguru import logger
from app.core.config import settings

# 内部单例连接池句柄（延迟到事件循环启动后或 Lifespan 初始化）
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


class DistributedSessionLock:
    """
    Cluster-Safe Distributed Mutex Lock (Redlock pattern):
    Prevents race conditions across multiple Kubernetes Pods for the same session_id/thread_id.
    """
    def __init__(self, thread_id: str, lease_seconds: int = 30):
        self.lock_key = f"lock:session:{thread_id}"
        self.lease_seconds = lease_seconds
        self.owner_token = str(uuid.uuid4())
        self.is_acquired = False

    async def acquire(self) -> bool:
        """Attempts to acquire the lock non-blockingly."""
        client = get_redis_client()
        success = await client.set(
            self.lock_key,
            self.owner_token,
            nx=True,
            ex=self.lease_seconds,
        )
        self.is_acquired = bool(success)
        return self.is_acquired

    async def release(self) -> None:
        """
        Safely releases the lock using a Lua script to ensure we only release
        locks that WE own (prevents accidentally releasing an expired lock acquired by another worker).
        """
        if not self.is_acquired:
            return

        lua_release_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        client = get_redis_client()
        try:
            await client.eval(
                lua_release_script,
                1,
                self.lock_key,
                self.owner_token,
            )
            logger.debug(f"【🔒】Distributed lock released for {self.lock_key}")
        except Exception as e:
            logger.error(f"Failed to release distributed lock for {self.lock_key}: {e}")
        finally:
            self.is_acquired = False
