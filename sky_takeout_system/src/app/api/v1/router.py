from fastapi import APIRouter
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.approval import router as approval_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.metrics import router as metrics_router

api_v1_router = APIRouter()

# Health check probes (/api/v1/healthz/liveness, /api/v1/healthz/readiness)
api_v1_router.include_router(health_router)

# Prometheus metrics scrape endpoint (/api/v1/metrics)
api_v1_router.include_router(metrics_router)

# Authentication endpoints (/api/v1/auth/login, /api/v1/auth/me)
api_v1_router.include_router(auth_router)

# Agent interactions & human approval (/api/v1/takeout/chat, /api/v1/takeout/approve)
api_v1_router.include_router(chat_router)
api_v1_router.include_router(approval_router)
