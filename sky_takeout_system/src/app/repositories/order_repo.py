from decimal import Decimal
from sqlalchemy import select
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BaseModel, Dish, Order


class OrderRepository:
    """
    data access repository for orders and logistics Telemetry
    """
    @staticmethod
    async def get_by_order_number(session: AsyncSession, order_number: str)->Optional[Order]:
        stmt = select(Order).where(Order.order_number == order_number)
        result = await session.execute(stmt)
        order = result.scalar_one_or_none()
        return order
