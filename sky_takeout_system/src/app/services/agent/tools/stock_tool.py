import json
from langchain_core.tools import tool
from loguru import logger
from app.core.database import AsyncSessionLocal
from app.repositories.dish_repo import DishRepository


@tool
async def inspect_and_reserve_dish_stock(dish_name: str, quantity: int = 1) -> str:
    """
    Queries real-time warehouse inventory in MySQL and atomically reserves dish availability.
    Returns structured JSON with stock status, prep time, or failure reason.
    """
    try:
        async with AsyncSessionLocal() as session:
            success, message, prep_time = await DishRepository.check_and_deduct_stock(
                session=session,
                name=dish_name,
                quantity=quantity
            )
            if success:
                await session.commit()
                return json.dumps({
                    "status": "SUCCESS",
                    "dish_name": dish_name,
                    "quantity": quantity,
                    "in_stock": True,
                    "prep_time_minutes": prep_time,
                    "message": "Stock successfully reserved."
                }, ensure_ascii=False)
            
            return json.dumps({
                "status": "OUT_OF_STOCK",
                "dish_name": dish_name,
                "in_stock": False,
                "message": message
            }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"❌ [stock_tool] Database error during stock check for '{dish_name}': {e}")
        return json.dumps({
            "status": "ERROR",
            "dish_name": dish_name,
            "in_stock": False,
            "message": "Kitchen stock service temporarily unavailable. Please recommend alternative dishes."
        }, ensure_ascii=False)
