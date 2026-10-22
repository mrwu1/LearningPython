from decimal import Decimal
from sqlalchemy import String, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel


class RefundLedger(BaseModel):
    """
    Financial Idempotency Refund Ledger:
    Guarantees strict idempotency for refund payouts.
    The unique constraint on order_number prevents double-spending at the database layer.
    """
    __tablename__ = "refund_ledgers"

    order_number: Mapped[str] = mapped_column(
        String(64),
        unique=True,  # 🌟 数据库级唯一键：彻底拦截重放攻击与多次打款！
        index=True,
        nullable=False,
        comment="Target order number (Idempotency Key)"
    )
    refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Actual disbursed refund amount"
    )
    risk_level: Mapped[str] = mapped_column(
        String(16),
        default="LOW",
        nullable=False,
        comment="Risk Level: LOW (<= 50) or HIGH (> 50)"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING_APPROVAL",
        nullable=False,
        comment="Status: PENDING_APPROVAL, APPROVED, REJECTED"
    )
    reason: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
        comment="Customer complaint or refund reason"
    )
    reviewer_notes: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
        comment="Manager approval notes"
    )
    tx_receipt: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Unique payout receipt voucher (e.g. TX_REFUND_xxx)"
    )