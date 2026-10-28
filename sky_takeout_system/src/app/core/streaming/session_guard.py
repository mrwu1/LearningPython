from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import HTTPException, status
from loguru import logger
from app.core.redis import RedissonLock

# 一个人同一时间只能在一个房间说话。防止用户手抖在手机上狂点
# 10下，把系统搞崩溃。对话完了自动把锁开开。
@asynccontextmanager # 👈 核心就在这个装饰器！
async def guard_stream_session(
    thread_id: str,
    lock_lease_seconds: int = 60
) -> AsyncGenerator[RedissonLock, None]:
    # 【前半部分】：进入 async with 时自动执行
    """Guarantees distributed lock acquisition and fail-safe release for streaming sessions."""
    lock = RedissonLock(
        f"session_lock:{thread_id}",
        lease_seconds=lock_lease_seconds,
        acquire_timeout=0.5
    )
    acquired = await lock.acquire()
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Session '{thread_id}' is currently busy. Please wait."
        )
    try:
        yield lock # 👈 把控制权交给你！此时开始执行 async with 里面的代码‼️‼️‼️
    finally:
        await lock.release()
        logger.info(f"🏁 [SessionGuard] Lock released for session {thread_id}")
