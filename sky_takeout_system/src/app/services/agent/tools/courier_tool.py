import json
from langchain_core.tools import tool
from loguru import logger
from app.core.database import AsyncSessionLocal
from app.repositories.order_repo import OrderRepository


@tool
async def query_courier_telemetry(order_number: str) -> str:
    """
    Queries live courier GPS telemetry, distance, and ETA for a takeout order from MySQL.
    Returns structured JSON with rider name, distance, status, and ETA.
    """
    try:
        async with AsyncSessionLocal() as session:
            order = await OrderRepository.get_by_order_number(session, order_number)
            if not order:
                return json.dumps({
                    "status": "NOT_FOUND",
                    "order_number": order_number,
                    "message": f"Order '{order_number}' not found in system. Please verify order ID."
                }, ensure_ascii=False)

            return json.dumps({
                "status": "FOUND",
                "order_number": order.order_number,
                "order_status": order.status,
                "courier_name": order.courier_name,
                "courier_distance_meters": order.courier_distance_meters,
                "delivery_eta_minutes": order.delivery_eta_minutes,
                "message": f"Courier '{order.courier_name}' is {order.courier_distance_meters}m away, arriving in ~{order.delivery_eta_minutes} mins."
            }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"❌ [courier_tool] Failed to fetch telemetry for order '{order_number}': {e}")
        return json.dumps({
            "status": "ERROR",
            "order_number": order_number,
            "message": "Courier GPS service temporarily unavailable. Please ask customer to wait a moment."
        }, ensure_ascii=False)
