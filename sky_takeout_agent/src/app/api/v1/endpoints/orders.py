import asyncio
from fastapi import APIRouter, HTTPException
from loguru import logger
from app.core.redis_client import redis_client

router = APIRouter(tags=["订单交易模块"])

@router.post("/orders/submit", summary="高并发防重下单 (Redis 异步分布式锁)")
async def submit_order(order_id: int):
    lock_key = f"lock:order:{order_id}"
    lock = redis_client.lock(lock_key, timeout=10, blocking=False)

    acquired = await lock.acquire()
    if not acquired:
        logger.warning(f"⚠️：the {order_id} is dealing to db, trigger the repeat warning")
        raise HTTPException(status_code=409, detail="service busy! please try again later")

    try:
        logger.info(f"🔒 start a new order_id {order_id}")
        await asyncio.sleep(3)
        logger.info("successful work!")
        return {"code": 200, "message": f"order {order_id} submit success"}
    finally:
        await lock.release()
        logger.info("the lock has been released successful!")
