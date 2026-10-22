from sqlalchemy import String, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel


class User(BaseModel):
    """
    User Entity: Represents platform customers and store managers.
    Inherits id, created_at, updated_at from BaseModel.
    """
    __tablename__ = "users"

    # 登录用户名 (唯一索引)
    username: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="Login username"
    )

    # bcrypt 加盐密码哈希 (严禁存明文)
    hashed_password: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Bcrypt password hash"
    )

    # 角色权限: ROLE_CUSTOMER (普通顾客) | ROLE_STORE_MANAGER (店长/审批人)
    role: Mapped[str] = mapped_column(
        String(32),
        default="ROLE_CUSTOMER",
        nullable=False,
        comment="RBAC Role: ROLE_CUSTOMER | ROLE_STORE_MANAGER"
    )

    # 业务会话身份 (例如关联订单的 USER_1001)
    user_identifier: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="Business identifier bound to orders (e.g. USER_1001)"
    )

    # 账号状态: 1-启用, 0-禁用
    status: Mapped[int] = mapped_column(
        SmallInteger,
        default=1,
        nullable=False,
        comment="Account status: 1-Active, 0-Disabled"
    )