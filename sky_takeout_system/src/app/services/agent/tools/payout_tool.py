import json
from decimal import Decimal
from langchain_core.tools import tool
from loguru import logger
from app.core.database import AsyncSessionLocal
from app.repositories.refund_repo import RefundRepository


@tool
async def execute_refund_payout(order_number: str, amount: float, reason: str = "Cold food complaint") -> str:
    """
    Executes financial payout with strict database-level idempotency protection.
    Guarantees zero double-spending even if retried or re-invoked by the model.
    Returns structured JSON with payout confirmation, status, and transaction voucher.
    """
    try:
        async with AsyncSessionLocal() as session:
            is_new, ledger, message = await RefundRepository.execute_or_get_refund(
                session=session,
                order_number=order_number,
                amount=Decimal(str(amount)),
                reason=reason,
                risk_level="LOW" if amount <= 50 else "HIGH",
                status="APPROVED",
                reviewer_notes="Approved via Takeout Agent System"
            )
            return json.dumps({
                "status": "APPROVED",
                "is_new_payout": is_new,
                "order_number": order_number,
                "refund_amount": float(ledger.refund_amount),
                "tx_receipt": ledger.tx_receipt,
                "message": message
            }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"❌ [payout_tool] Failed to execute payout for order '{order_number}': {e}")
        return json.dumps({
            "status": "ERROR",
            "order_number": order_number,
            "refund_amount": amount,
            "message": "Payment gateway temporarily busy. Please contact human customer service."
        }, ensure_ascii=False)
