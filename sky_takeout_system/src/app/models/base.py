# 1.
# 实体通用基类
# src / app / models / base.py（主键ID、自动审计时间戳 created_at / updated_at）；
from datetime import datetime

from sqlalchemy import DateTime, func, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TimestampMixin(object):
    """
    automatically tracks creation and modification of timestamps using database functions
    """
    created_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Creation timestamp"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last update timestamp"
    )

class BaseModel(Base,TimestampMixin):
    """
    abstract base entity:
    provides auto-incrementing  bigint id and audit timestamp for all domain models
    """
    __abstract__ = True
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="Primary Key ID"
    )