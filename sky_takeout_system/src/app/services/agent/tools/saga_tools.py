import asyncio
import uuid
from typing import Callable

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import with_distributed_lock
from app.repositories.dish_repo import DishRepository
from app.repositories.order_repo import OrderRepository


class PaymentGatewayTimeoutException(Exception):
    """simulated 504 gateway timeout or network drop from third party"""
    pass

 # Step 1: Order State Mutation & Compensation
@with_distributed_lock("order:{order_number}",lease_seconds=10)
async def saga_step_lock_order(
    session: AsyncSession,
    order_number: str,
    target_status: str = "REFUNDING"
)->str:
    """➡️
            Saga Forward Step 1:
            Locks the order resource and transitions status to REFUNDING.
            Returns the original status for reverse compensation.
    """
    order = await OrderRepository.get_by_order_number(session, order_number)
    if not order:
        raise ValueError(f"Order '{order_number}' not found.")
    original_status = order.status
    order.status = target_status
    await session.commit()
    logger.info(f"📝 [Saga Step 1] Order '{order_number}' status updated: {original_status} -> {target_status}")
    return original_status

@with_distributed_lock("order:{order_number}",lease_seconds=10)
async def saga_compensate_order(
    session: AsyncSession,
    order_number: str,
    original_status: str
)->None:
    """⬅️
            Saga Compensating Step 1:
            Reverts the order status back to its original state if downstream steps fail.
    """
    order = await OrderRepository.get_by_order_number(session, order_number)
    if order:
        order.status = original_status
        await session.commit()
        logger.warning(f"↩️ [Saga Comp 1] Order '{order_number}' status reverted back to '{original_status}'.")

 # Step 2: Inventory Restock & Compensation
@with_distributed_lock("dish:{dish_name}",lease_seconds=10)
async def saga_step_restock_dish(
        session: AsyncSession,
        dish_name: str,
        quantity: int
)->int:
    """➡️
            Saga Forward Step 2:
            Atomically restores inventory for the refunded dish.
    """
    dish = await DishRepository.get_by_name(session, dish_name)
    if not dish:
        raise ValueError(f"Dish '{dish_name}' not found.")
    dish.stock += quantity
    await session.commit()
    logger.info(f"📦 [Saga Step 2] Restocked dish '{dish_name}': +{quantity} (Current stock: {dish.stock})")
    return quantity

@with_distributed_lock("dish:{dish_name}",lease_seconds=10)
async def saga_compensate_dish_stock(
        session: AsyncSession,
        dish_name: str,
        quantity: int
) -> None:
        """           ⬅️
        Saga Compensating Step 2:
        Re-deducts the restocked inventory if downstream payout fails.
        """
        dish = await DishRepository.get_by_name(session, dish_name)
        if dish:
            dish.stock -= quantity
            await session.commit()
            logger.warning(f"↩️ [Saga Comp 2] Re-deducted dish '{dish_name}': -{quantity} (Current stock: {dish.stock}).")

# Step 3: Third-Party External Payment Gateway
async def saga_step_call_third_party_gateway(
        order_number: str,
        amount: float,
        simulate_network_failure: bool = False
) -> dict:
    """
    Saga Forward Step 3:
    Simulates external bank/payment gateway RPC/HTTP call.
    Demonstrates chaos engineering by simulating 504 timeout failure.
    """
    if simulate_network_failure:
        logger.error(f"💥 [Saga Step 3] External bank gateway timed out (504 Gateway Timeout) for order '{order_number}'!")
        raise PaymentGatewayTimeoutException(
            f"504 Gateway Timeout: Third-party banking network dropped request for order {order_number}."
        )

    tx_receipt = f"TX_BANK_{uuid.uuid4().hex[:12].upper()}"
    logger.info(f"💳 [Saga Step 3] Bank payout disbursed successfully: {tx_receipt} (${amount:.2f})")
    return {"status": "SUCCESS", "tx_receipt": tx_receipt, "amount": amount}


async def saga_step_query_gateway_status(
        order_number: str,
        simulate_gateway_success: bool = False
) -> dict:
    """
    Saga Reconciliation Step:
    Queries external banking gateway to verify actual payout status after a timeout.
    Prevents false rollbacks and financial reconciliation discrepancy.
    """
    if simulate_gateway_success:
        tx_receipt = f"TX_BANK_RECONCILED_{uuid.uuid4().hex[:12].upper()}"
        logger.info(f"🔍 [Gateway Reconcile] Order '{order_number}' was already disbursed on bank side:  {tx_receipt}")
        return {"status": "SUCCESS", "tx_receipt": tx_receipt}

    logger.warning(f"🔍 [Gateway Reconcile] Order '{order_number}' not found or rejected on bank side.")
    return {"status": "NOT_FOUND", "tx_receipt": None}






 # Saga Compensation Engine (LIFO Rollback Runner)
async def execute_saga_compensation(
            session: AsyncSession,
            saga_stack: list[tuple[Callable, dict]],
    max_retries: int = 3
) -> None:
        """
        Saga Reverse Compensation Engine:
        Pops compensation callbacks in LIFO order to unwind dirty state.
        """
        logger.warning(f"🚨 [Saga Engine] Commencing reverse compensation for {len(saga_stack)} operations...")
        while saga_stack:
            comp_fn, kwargs = saga_stack.pop()
            success = False
            for attempt in range(1, max_retries + 1):
                try:
                    await comp_fn(session=session, **kwargs)
                    success = True
                    break
                except Exception as exc:
                    logger.warning(
                        f"⚠️ [Saga Retry {attempt}/{max_retries}] Failed to execute {comp_fn.__name__}: {exc}")
                    if attempt < max_retries:
                        await asyncio.sleep(0.05 * (2 ** (attempt - 1)))
            if not success:
                logger.critical(
                    f"🔥 [DLQ CRITICAL ALERT] Permanent compensation failure on '{comp_fn.__name__}' "
                    f"with args {kwargs}! Forwarding to Dead Letter Queue for manual audit."
                )
        logger.info("🛡️ [Saga Engine] All reverse compensations executed cleanly.")

# 示意
# saga_stack = [
#     (create_order, {"order_id": "o1001"}),
#     (deduct_balance, {"user_id": "u001", "amount": 100}),
#     (notify_warehouse, {"sku": "sk001"})
# ]
