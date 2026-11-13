from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

router = APIRouter(tags=["Observability & Telemetry"])


@router.get("/metrics")
async def prometheus_metrics_endpoint():
    """Exposes Prometheus application metrics for scraping by Prometheus and Grafana."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
