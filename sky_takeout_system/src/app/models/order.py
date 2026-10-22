from decimal import Decimal


from sqlalchemy import String, Numeric, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Order(BaseModel):
    """
    Takeout Order and Delivery Telemetry Entity:
    Tracks order lifecycle, customer ID, and real-time courier GPS coordinates.
    """
    __tablename__ = "orders"

    order_number: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="Unique business order number"
    )
    user_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        comment="Customer user identifier"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Total order price"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="CONFIRMED",
        nullable=False,
        comment="Order Status: PENDING, CONFIRMED, DELIVERING, COMPLETED, REFUNDED"
    )
    courier_name: Mapped[str] = mapped_column(
        String(64),
        default="Courier Xiao Wang",
        nullable=False,
        comment="Assigned courier name"
    )
    courier_distance_meters: Mapped[int] = mapped_column(
        Integer,
        default=850,
        nullable=False,
        comment="Current courier distance from customer in meters"
    )
    delivery_eta_minutes: Mapped[int] = mapped_column(
        Integer,
        default=6,
        nullable=False,
        comment="Estimated arrival duration in minutes"
    )