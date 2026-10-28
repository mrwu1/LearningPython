import asyncio
import random
import uuid
from typing import Optional

from loguru import logger

from app.core.redis import get_redis_client, RedisLockError
from app.core.redis.lock_context import (
    get_ctx_tokens, set_ctx_token, pop_ctx_token,
)
from app.core.redis.lua_scripts import LUA_ACQUIRE, LUA_RELEASE, LUA_RENEW


class RedissonLock:
    """
    生产级 Redisson 兼容分布式锁：
      1. 可重入：Redis Hash 计数器 + 实例级本地计数双保险
      2. 看门狗：后台协程周期续期，续期失败触发 lock_lost 通知
      3. contextvars 协程继承：嵌套调用自动重入，context 独立不串锁
      4. 脚本缓存：复用 register_script，避免每次传全文
      5. 可观测性：lock_lost 事件 + get_owner/is_locked 查询接口
    """

    def __init__(
        self,
        resource_key: str,
        lease_seconds: int = 30,
        acquire_timeout: float = 5.0,
        retry_interval_ms: int = 40,
        auto_renew: bool = True,
    ):
        if lease_seconds < 3:
            raise ValueError("lease_seconds must be >= 3 to allow watchdog renewal")

        self.resource_key = resource_key
        self.lock_key = f"lock:redisson:{resource_key}"
        self.channel_key = f"channel:lock:redisson:{resource_key}"
        self.lease_seconds = lease_seconds
        self.lease_ms = int(lease_seconds * 1000)
        self.acquire_timeout = acquire_timeout
        self.retry_interval_ms = retry_interval_ms
        self.auto_renew = auto_renew

        # 从 context 继承 token（重入）或生成新 token
        ctx_tokens = get_ctx_tokens()
        if resource_key in ctx_tokens:
            self.owner_token = ctx_tokens[resource_key]
            self._is_reentrant = True
        else:
            self.owner_token = uuid.uuid4().hex[:16]
            self._is_reentrant = False

        # 实例级重入计数（修复：is_acquired 布尔无法表达重入）
        self._local_count = 0
        # 是否真正持有锁（与 _local_count > 0 同步）
        self.is_acquired = False

        self._watchdog_task: Optional[asyncio.Task] = None
        # 锁丢失通知：业务可 await 此事件感知"锁没了"
        self._lock_lost = asyncio.Event()

        # 脚本缓存（首次 eval 后由 redis-py register_script 缓存 SHA）
        self._acquire_script = None
        self._release_script = None
        self._renew_script = None

    # ------------------------------------------------------------------
    # 内部：脚本缓存
    # ------------------------------------------------------------------
    def _ensure_scripts(self):
        if self._acquire_script is not None:
            return
        client = get_redis_client()
        self._acquire_script = client.register_script(LUA_ACQUIRE)
        self._release_script = client.register_script(LUA_RELEASE)
        self._renew_script = client.register_script(LUA_RENEW)

    # ------------------------------------------------------------------
    # 看门狗
    # ------------------------------------------------------------------
    def _renew_interval(self) -> float:
        # lease/3，下限 1s，上限 10s（避免长 lease 故障窗口过大）
        return min(10.0, max(1.0, self.lease_seconds / 3.0))

    async def _watchdog_loop(self) -> None:
        interval = self._renew_interval()
        logger.debug(f"🐶 [Watchdog] Started for '{self.lock_key}' (interval={interval:.1f}s)")

        consecutive_failures = 0
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    res = await self._renew_script(
                        keys=[self.lock_key],
                        args=[self.lease_ms, self.owner_token],
                    )
                except Exception as e:
                    consecutive_failures += 1
                    logger.error(
                        f"🐶 ❌ [Watchdog] Renew error for '{self.lock_key}' "
                        f"(attempt={consecutive_failures}): {e}"
                    )
                    # 网络抖动容忍：连续 3 次失败才认为锁丢失
                    if consecutive_failures >= 3:
                        self._mark_lock_lost("renew_exception")
                        break
                    continue

                consecutive_failures = 0
                if res == 1:
                    logger.debug(f"🐶 [Watchdog] Renewed '{self.lock_key}' -> {self.lease_seconds}s")
                else:
                    # field 不匹配 => 锁已被删/被他人持有
                    logger.warning(f"🐶 [Watchdog] Lock '{self.lock_key}' gone, stopping.")
                    self._mark_lock_lost("field_mismatch")
                    break
        except asyncio.CancelledError:
            logger.debug(f"🐶 [Watchdog] Cancelled for '{self.lock_key}'.")
            raise

    def _mark_lock_lost(self, reason: str) -> None:
        if not self._lock_lost.is_set():
            logger.error(f"🚨 [RedissonLock] LOCK LOST '{self.lock_key}' reason={reason}")
            self._lock_lost.set()

    # ------------------------------------------------------------------
    # 公开：锁丢失监听
    # ------------------------------------------------------------------
    @property
    def lock_lost(self) -> asyncio.Event:
        """业务可 `await lock.lock_lost.wait()` 感知锁丢失（Redis 故障、被删等）。"""
        return self._lock_lost

    # ------------------------------------------------------------------
    # 加锁
    # ------------------------------------------------------------------
    async def acquire(self) -> bool:
        self._ensure_scripts()
        start = asyncio.get_running_loop().time()
        attempt = 0

        while True:
            result = await self._acquire_script(
                keys=[self.lock_key],
                args=[self.lease_ms, self.owner_token],
            )

            if result == 1:
                self.is_acquired = True
                self._local_count += 1

                # 写入 context（供内层嵌套 acquire 重入）
                set_ctx_token(self.resource_key, self.owner_token)

                # 关键修复：只有非重入 + auto_renew + 无看门狗时才启动
                if self.auto_renew and not self._is_reentrant and self._watchdog_task is None:
                    self._watchdog_task = asyncio.create_task(self._watchdog_loop())

                logger.debug(
                    f"🔒 [RedissonLock] Acquired '{self.lock_key}' "
                    f"(reentrant={self._is_reentrant}, local_count={self._local_count})"
                )
                return True

            elapsed = asyncio.get_running_loop().time() - start
            if elapsed > self.acquire_timeout:
                logger.warning(f"⏳ [RedissonLock] Timeout '{self.lock_key}' after {elapsed:.2f}s")
                return False

            attempt += 1
            # 指数退避 + jitter，封顶 500ms
            base = min(self.retry_interval_ms / 1000.0 * (2 ** min(attempt, 4)), 0.5)
            await asyncio.sleep(base * random.uniform(0.8, 1.2))

    # ------------------------------------------------------------------
    # 释放
    # ------------------------------------------------------------------
    async def release(self) -> None:
        if self._local_count <= 0:
            return

        self._ensure_scripts()
        try:
            res = await self._release_script(
                keys=[self.lock_key, self.channel_key],
                args=[self.owner_token],
            )

            if res == 1:
                # 完全释放：停看门狗 + 清 context
                if self._watchdog_task and not self._watchdog_task.done():
                    self._watchdog_task.cancel()
                    try:
                        await self._watchdog_task
                    except asyncio.CancelledError:
                        pass
                    self._watchdog_task = None
                pop_ctx_token(self.resource_key)
                logger.debug(f"🔓 [RedissonLock] Fully released '{self.lock_key}'")
            elif res == 0:
                logger.debug(
                    f"🔓 [RedissonLock] Decremented '{self.lock_key}' "
                    f"(remaining_local={self._local_count - 1})"
                )
            elif res == -1:
                logger.warning(f"⚠️ [RedissonLock] Release unowned lock '{self.lock_key}'")
        except Exception as e:
            logger.error(f"🔓 ❌ [RedissonLock] Release failed '{self.lock_key}': {e}")
            raise  # 释放失败不吞异常，让业务决定重试
        finally:
            self._local_count = max(0, self._local_count - 1)
            if self._local_count == 0:
                self.is_acquired = False

    # ------------------------------------------------------------------
    # 可观测性
    # ------------------------------------------------------------------
    async def is_locked(self) -> bool:
        client = get_redis_client()
        return bool(await client.exists(self.lock_key))

    async def get_owner(self) -> Optional[str]:
        client = get_redis_client()
        owners = await client.hkeys(self.lock_key)
        return owners[0] if owners else None

    # ------------------------------------------------------------------
    # 上下文管理
    # ------------------------------------------------------------------
    async def __aenter__(self):
        ok = await self.acquire()
        if not ok:
            raise RedisLockError(
                f"Could not acquire '{self.lock_key}' within {self.acquire_timeout}s"
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()