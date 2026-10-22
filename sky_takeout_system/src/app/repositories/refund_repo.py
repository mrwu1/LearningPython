import uuid
from decimal import Decimal
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, RefundLedger


class RefundRepository:
    """
    data access repository for financial payouts and idempotent ledgers
    """
    @staticmethod
    async def get_by_order_number(session: AsyncSession, order_number: str)->Optional[RefundLedger]:
        stmt = select(RefundLedger).where(RefundLedger.order_number == order_number)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def execute_or_get_refund(
            session: AsyncSession,
            order_number: str,
            amount: Decimal,
            reason: str,
            risk_level: str = "LOW",
            status: str = "APPROVED",
            reviewer_notes: str = "Auto-approved small amount"
    )->tuple[bool,RefundLedger,str]:
        """
                    Atomic Transaction with Database Idempotency Guard:
                    If order_number already exists, returns the existing record (idempotency hit).
                    If not, atomically records payout voucher and updates order status.
        """
        # 1. 先查幂等账本：如果已存在，触发幂等防重放护盾！
        existing = await RefundRepository.get_by_order_number(session, order_number)
        if existing:
            logger.warning(
                f"🛡️ [Idempotency Shield] Order {order_number} already in refund ledger! "
                f"Status: {existing.status} | Voucher: {existing.tx_receipt}"
            )
            return False, existing, f"IDEMPOTENCY_CACHE_HIT: Order {order_number} refund already recorded ({existing.status})"
        # 2. 如果不存在，生成全球唯一打款凭证并入库
        tx_receipt = f"TX_PAYOUT_{uuid.uuid4().hex[:12].upper()}"
        new_ledger = RefundLedger(
            order_number=order_number,
            refund_amount=amount,
            risk_level=risk_level,
            status=status,
            reason=reason,
            reviewer_notes=reviewer_notes,
            tx_receipt=tx_receipt
        )
        session.add(new_ledger)
        # 3. 联动更新订单状态为已退款
        order_stmt = select(Order).where(Order.order_number == order_number)
        order_result = await session.execute(order_stmt)
        order = order_result.scalar_one_or_none()
        if order:
            order.status = "REFUNDED" if status == "APPROVED" else "REFUNDING"
        await session.commit()
        await session.refresh(new_ledger)
        logger.info(f"💰 [Financial Payout Recorded] Order {order_number} refunded ${amount} | Receipt: {tx_receipt}")
        return True, new_ledger, f"SUCCESS: Payout {tx_receipt} processed successfully"