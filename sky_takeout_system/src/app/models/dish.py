

from decimal import Decimal
from sqlalchemy import String, Numeric, Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel

class Dish(BaseModel):

    __tablename__ = "dishes"

    name: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="Name of dish"
    )
    price:Mapped[Decimal] = mapped_column(
        Numeric(10,2),
        default=0,
        nullable=False,
        comment="Price of dish"
    )
    stock: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Kitchen warehouse inventory stock"
    )
    prep_time_minutes:Mapped[int] = mapped_column(
        Integer,
        default=15,
        nullable=False,
        comment="Time spent in minutes"
    )
    status:Mapped[int] = mapped_column(
        SmallInteger,
        default=1,
        nullable=False,
        comment="Status of dish"
    )
    version: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Optimistic locking version counter"
    )

