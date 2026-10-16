from fastapi import APIRouter
from app.api.v1.endpoints import system, auth, dishes, orders, tasks

api_router = APIRouter()

# 统一汇聚挂载各个业务子路由
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(dishes.router)
api_router.include_router(orders.router)
api_router.include_router(tasks.router)
