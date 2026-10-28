# 只专注于
# LangGraph
# SSE
# 长连接场景下的会话防抖（Non - blocking, Fail - Fast）：
# 会话级场景特化锁
import uuid

from loguru import logger

from app.core.redis.client import get_redis_client


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