from fastapi import APIRouter
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.approval import router as approval_router

from app.api.v1.endpoints.auth import router as auth_router  # 👈 Import auth router

api_v1_router = APIRouter()

# 挂载健康检查探针 (/api/v1/healthz/liveness, /api/v1/healthz/readiness)
api_v1_router.include_router(health_router)

# Mount authentication endpoints (/api/v1/auth/login, /api/v1/auth/me)
api_v1_router.include_router(auth_router)  # 👈 Mount here

# 挂载智能体业务接口 (/api/v1/takeout/chat, /api/v1/takeout/approve)
api_v1_router.include_router(chat_router)
api_v1_router.include_router(approval_router)
