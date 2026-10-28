from typing import Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas.user import UserCreate


class UserRepository:

    @staticmethod
    async def get_by_user(session: AsyncSession, username: str) -> Optional[User]:
        stmt = select(User).where(User.username == username)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_identifier(session: AsyncSession, identifier: str) -> Optional[User]:
        """Query user by business user_identifier (e.g. USER_1001)."""
        stmt = select(User).where(and_(User.user_identifier == identifier, User.status == 1))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_user(session: AsyncSession, user_in: UserCreate) -> User:
        user = User(**user_in.model_dump())
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user