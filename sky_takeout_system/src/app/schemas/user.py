from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """DTO for creating a new user."""
    username: str = Field(..., description="登录用户名")
    hashed_password: str = Field(..., description="加盐哈希密码")
    role: str = Field(default="ROLE_CUSTOMER", description="角色: ROLE_CUSTOMER | ROLE_STORE_MANAGER")
    user_identifier: str = Field(..., description="业务ID (如 USER_1001)")


class UserResponse(BaseModel):
    """DTO for returning user profile."""
    id: int
    username: str
    role: str
    user_identifier: str
    status: int

    class Config:
        from_attributes = True