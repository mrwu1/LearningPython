"""
    Redis Infrastructure Package Facade:
    Re-exports client lifecycle, distributed locks, and decorators for backwards compatibility.
    """
from app.core.redis.client import get_redis_client, close_redis_client
from app.core.redis.lua_scripts import LUA_RELEASE_LOCK_SCRIPT, LUA_SLIDING_WINDOW_SCRIPT
from app.core.redis.mutex import RedisLock, RedisLockError
from app.core.redis.decorators import with_distributed_lock
from app.core.redis.session_lock import DistributedSessionLock
from app.core.redis.redisson_lock import RedissonLock

__all__ = [
    "get_redis_client",
    "close_redis_client",
    "LUA_RELEASE_LOCK_SCRIPT",
    "LUA_SLIDING_WINDOW_SCRIPT",
    "RedisLock",
    "RedisLockError",
    "with_distributed_lock",
    "DistributedSessionLock",
    "RedissonLock"
]