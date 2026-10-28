import asyncio
import random
import time
import uuid

from loguru import logger

from app.core.redis.client import get_redis_client
from app.core.redis.lua_scripts import LUA_RELEASE_LOCK_SCRIPT


# 只管 SET NX EX、自旋重试、Jitter 退避和 Lua 释放，没有任何装饰器和特化业务逻辑：

class RedisLockError(Exception):
    """Raised when a distributed lock cannot be acquired within timeout window."""
    pass

class RedisLock:
    """
           Enterprise-Grade Distributed Mutex Lock Primitive (Redlock Pattern):
           Provides spin-wait retry with jitter, non-blocking / blocking modes,
           and atomic Lua script release.
   """
    def __init__(
            self,
            resource_key:str,
            lease_seconds: int = 15,
            acquire_timeout: float = 3,
            retry_interval_ms: int = 30

    ):
        self.lock_key = f"lock:{resource_key}"
        self.resource_key = resource_key
        self.lease_seconds = lease_seconds
        self.acquire_timeout = acquire_timeout
        self.retry_interval_ms = retry_interval_ms
        self.owner_token = str(uuid.uuid4())
        self.is_acquired = False

    async def acquire(self) -> bool:
        """Attempts to acquire lock with spin-wait retry until timeout."""
        client = get_redis_client()
        start_time = asyncio.get_running_loop().time()
        while True:
            success = await client.set(
                self.lock_key,
                self.owner_token,
                nx=True,
                ex = self.lease_seconds
            )
            if success:
                self.is_acquired = True
                logger.debug(f"🔒 [RedisLock] Acquired lock for '{self.lock_key}'")
                return True
            elapsed = asyncio.get_running_loop().time() - start_time
            if elapsed > self.acquire_timeout:
                logger.warning(f"⏳ [RedisLock] Timed out waiting for '{self.lock_key}' after {elapsed:.2f}s")
                return False
            # 指数退避加随机抖动，彻底消灭惊群效应 (Thundering Herd)
            jitter = random.uniform(0.8, 1.2)
            sleep_duration = (self.retry_interval_ms / 1000.0) * jitter
            await asyncio.sleep(sleep_duration)
    async def release(self) -> None:
        """Atomically releases lock using Lua script only if owner_token matches."""
        if not self.is_acquired:
            return
        client = get_redis_client()
        try:
            await client.eval(LUA_RELEASE_LOCK_SCRIPT,1,self.lock_key,self.owner_token)
            logger.debug(f"🔓 [RedisLock] Released lock for '{self.lock_key}'")
        except Exception as e:
            logger.error(f"🔓  ❌Failed to release RedisLock '{self.lock_key}': {e}")
        finally:
            self.is_acquired = False
    # - 进入 `async with` 代码块时**自动执行**，返回值会赋值给 `as` 后面的变量
    async def __aenter__(self):
        acquire = await self.acquire()
        if not acquire:
            raise RedisLockError(f"Could not acquire lock for '{self.lock_key}' within {self.acquire_timeout}s.")
        return self
    # 退出代码块时**自动执行**
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()
# 1. 不支持**可重入**
# 2. 只有基础自旋 + jitter，没有看门狗，业务执行超时会丢锁
#
# >
# > 分布式 ≠ 高可用。
# > 「分布式锁」的定义：**多台机器上的多个进程 / 协程争抢同一个资源，互斥**，只要共用一套 Redis，就满足分布式。
# > 而**RedLock（红锁）**才是多 Redis 实例高可用版本，是另一个东西。