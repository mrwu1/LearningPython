from typing import Callable

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.database import AsyncSessionLocal
from app.core.security import decode_access_token
from app.models import User
from app.repositories.user_repo import UserRepository

# HTTPBearer extracts "Authorization: Bearer <token>" without enforcing form-data
security_schema = HTTPBearer(auto_error=False)


# use：session: AsyncSession = Depends(get_db_session)
async def get_db_session():
    """Dependency yielding an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"❌[get_db_session]:{e}")
            await session.rollback()
            raise e

async def get_current_user(
        credentials:HTTPAuthorizationCredentials = Depends(security_schema),
        session:AsyncSession = Depends(get_db_session)
)->User:
    if not credentials:
        raise HTTPException(
            status_code=401,
        )
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_identifier:str = payload.get('sub')
        if not user_identifier:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload: missing subject identifier.",
                headers={"WWW-Authenticate": "Bearer"}
            )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signature has expired or is invalid.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    # Verify that the user still exists and remains active in MySQL
    user = await UserRepository.get_by_identifier(session,user_identifier)
    if not user: #`None`、`False`、`0`、`""`、`[]`、`{}`、空 ORM 集合对象
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user

def require_role(required_role:str)->Callable:
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role: #⚠️ equal
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Operation requires '{required_role}' permissions."
            )
        return current_user

    return role_checker