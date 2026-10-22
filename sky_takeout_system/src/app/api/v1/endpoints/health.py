import psycopg
from fastapi import APIRouter, Response, status
from sqlalchemy import text
from app.core.config import settings
from app.core.database import async_engine
from app.core.redis import get_redis_client
from app.schemas.takeout import HealthCheckResponse

router = APIRouter(prefix="/healthz", tags=["Infrastructure Health Probes"])


@router.get("/liveness")
async def liveness_probe():
    """K8s Liveness Probe: Confirms the process is running."""
    return {"status": "ALIVE", "app_name": settings.APP_NAME}


@router.get("/readiness", response_model=HealthCheckResponse)
async def readiness_probe(response: Response):
    """
    K8s Readiness Probe:
    Actively pings MySQL, Redis, and PostgreSQL to verify traffic readiness.
    Returns HTTP 503 if any core dependency is unhealthy.
    """
    mysql_ok = False
    redis_ok = False
    pg_ok = False

    # 1. Ping MySQL
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1;"))
            mysql_ok = True
    except Exception:
        mysql_ok = False

    # 2. Ping Redis
    try:
        client = get_redis_client()
        pong = await client.ping()
        redis_ok = (pong is True or pong == "PONG")
    except Exception:
        redis_ok = False

    # 3. Ping PostgreSQL Checkpointer
    try:
        conninfo = (
            f"postgresql://{settings.PG_USER}:{settings.PG_PASSWORD}"
            f"@{settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_DB}"
        )
        async with await psycopg.AsyncConnection.connect(conninfo, connect_timeout=3) as aconn:
            async with aconn.cursor() as cur:
                await cur.execute("SELECT 1;")
                pg_ok = True
    except Exception:
        pg_ok = False

    all_healthy = mysql_ok and redis_ok and pg_ok
    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthCheckResponse(
        status="HEALTHY" if all_healthy else "UNHEALTHY",
        mysql=mysql_ok,
        redis=redis_ok,
        postgres=pg_ok,
        app_name=settings.APP_NAME
    )
