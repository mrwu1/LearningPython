import asyncio
from decimal import Decimal
from sqlalchemy import select, update
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dish


class DishRepository:
    """
    data access repository for kitchen and warehouse stock
    """
    @staticmethod
    async def get_by_name(session: AsyncSession, name: str)->Optional[Dish]:
        stmt = select(Dish).where(Dish.name == name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_available(session: AsyncSession) -> list[Dish]:
        stmt = select(Dish).where(Dish.status == 1)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def check_and_deduct_stock1(
        session: AsyncSession,
        name: str,
        quantity: int
    ) -> tuple[bool, str, int]:
        """
        Pessimistic Row Lock (SELECT ... FOR UPDATE):
        Safely checks and deducts kitchen inventory without concurrency race conditions.
        Returns: (success: bool, message: str, prep_time_minutes: int)
        """
        # stmt = select(Dish).where(Dish.name == name).with_for_update()
        # result = await session.execute(stmt)
        # dish = result.scalar_one_or_none()
        # if not dish:
        #     return False, f"Dish '{name}' not found on menu", 0
        # if dish.status != 1:
        #     return False, f"Dish '{name}' is currently unavailable", 0
        # if dish.stock < quantity:
        #     return False, f"Insufficient stock for '{name}' (Stock: {dish.stock}, Wanted: {quantity})", dish.prep_time_minutes
        #
        # # 原子扣减库存
        # dish.stock -= quantity
        # return True, "Stock deducted successfully", dish.prep_time_minutes

        #✅ 优化为：Optimistic lock
        # 1. 乐观原子扣减：利用数据库行写锁的瞬间原子性，条件不满足则 rowcount == 0
        stmt = update(Dish).where(
            Dish.name == name,
                        Dish.status==1,
                        Dish.stock>=quantity
        ).values(stock = Dish.stock - quantity)
        result = await session.execute(stmt)

        if result.rowcount>0:
            # 查一下出餐时间用于向用户反馈（轻量只读，无任何锁）
            dish = await DishRepository.get_by_name(session, name)
            prep_time = dish.prep_time_minutes if dish else 15
            return True, "Stock deducted successfully (Optimistic CAS)", prep_time
        # 3. 如果 rowcount == 0，说明扣减失败：做一次轻量只读查询，分析失败原因
        else:
            dish = await DishRepository.get_by_name(session, name)
            if not dish:
                return False, f"Dish '{name}' not found on menu", 0
            if dish.status != 1:
                return False, f"Dish '{name}' is currently unavailable", 0
            if dish.stock < quantity:
                return False, f"Insufficient stock for '{name}' (Stock: {dish.stock}, Wanted: {quantity})", dish.prep_time_minutes

    # ✅ 优化为：optimistic lock with version and spin-retry / cas
    # thought:  改为“先读取 version，更新时带上 version = old_version，若冲突则循环重试”：
    @staticmethod
    async def check_and_deduct_stock(#check_and_deduct_stock_redis_distribute
            session: AsyncSession,
            name: str,
            quantity: int,
            max_retries: int = 3  # 版本冲突时的重试次数
    ) -> tuple[bool, str, int]:
        for attempt in range(max_retries):
            # 步骤 1: 普通无锁查询获取当前版本号
            dish = await DishRepository.get_by_name(session, name)
            if not dish:
                return False, f"Dish '{name}' not found on menu", 0
            if dish.status != 1:
                return False, f"Dish '{name}' is currently unavailable", 0
            if dish.stock < quantity:
                return False, f"Insufficient stock (Stock: {dish.stock})", dish.prep_time_minutes
            # 步骤 2: 携带 old_version 乐观更新，同时将版本号 + 1
            old_version = dish.version
            stmt = (
                update(Dish)
                .where(
                    Dish.name == name,
                       Dish.version == old_version
                )
                .values(
                    stock = Dish.stock - quantity,
                    version = old_version+1
                )
            )
            result = await session.execute(stmt)
            if result.rowcount>0:
                return True, "Stock deducted successfully", dish.prep_time_minutes
            # rowcount == 0 说明在步骤1和步骤2之间被其他并发请求抢先修改了版本，进入下一轮重试
            await asyncio.sleep(0.01 * (attempt + 1))  # 适度退避

        return False, f"Stock deduction failed after {max_retries} concurrent conflict retries", 0




