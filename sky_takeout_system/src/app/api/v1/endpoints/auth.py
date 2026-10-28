from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.api.deps import get_db_session, get_current_user
from app.core.security import verify_password, create_access_token
from app.models import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import TokenResponse, LoginRequest
from app.schemas.user import UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication & Access Tokens"])


@router.post("/login", response_model=TokenResponse)
async def login_endpoint(
        payload: LoginRequest,
        session: AsyncSession = Depends(get_db_session),
):
    user = await UserRepository.get_by_user(session, payload.username)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    token_payload={
        "sub": user.user_identifier,
         "role": user.role,
         "username": user.username
    }
    token = create_access_token(data=token_payload)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role=user.role,
        user_identifier=user.user_identifier
    )
@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
        """Protected Endpoint: Returns authenticated user profile."""
        return current_user