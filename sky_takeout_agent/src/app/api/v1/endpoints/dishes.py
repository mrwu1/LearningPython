import json
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy import select
from loguru import logger

from app.api.deps import SessionDep, check_role
from app.core.redis_client import redis_client
from app.models.dish import Dish

router = APIRouter(tags=["菜品模块"])

@router.get("/dishes", summary="异步查询菜品列表 (DB 直连)")
async def list_dishes(session: SessionDep):
    stmt = select(Dish).limit(5)
    result = await session.execute(stmt)
    dishes = result.scalars().all()
    return {
        "total": len(dishes),
        "data": [
            {"id": d.id, "name": d.name, "price": float(d.price), "status": d.status}
            for d in dishes
        ]
    }

@router.get("/dishes_redis", summary="异步查询菜品列表 (Redis Cache-Aside)")
async def list_dishes_with_cache(session: SessionDep):
    cache_key = "sky:takeout:dishes:top5"
    cached_data = await redis_client.get(cache_key)
    logger.info(f"the result for redis:{cached_data}")

    if not cached_data:
        stmt = select(Dish).limit(5)
        result = await session.execute(stmt)
        dishes = result.scalars().all()
        query = {
            "total": len(dishes),
            "data": [
                {"id": d.id, "name": d.name, "price": float(d.price), "status": d.status}
                for d in dishes
            ]
        }
        await redis_client.set(cache_key, json.dumps(query), ex=60)
        logger.info("the sql result has been write into redis.")
        return query

    logger.info(f"return redis query result directly!{cached_data}")
    return json.loads(cached_data)

@router.post("/admin/dishes", summary="管理员专有菜品创建接口")
async def admin_create_dish(admin_user: Annotated[dict, Depends(check_role("ADMIN"))]):
    return {"message": "操作成功：管理员已完成菜品配置", "operator": admin_user["username"]}
