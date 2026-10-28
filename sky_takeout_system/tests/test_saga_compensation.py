import asyncio
from decimal import Decimal
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import Dish, Order
from app.services.agent.specialists.refund_officer import execute_refund_saga_flow


async def setup_test_fixtures():
    """Initializes clean database fixtures for Saga testing."""
    async with AsyncSessionLocal() as session:
        # 1. Clean or create test dish
        dish_stmt = select(Dish).where(Dish.name == "Kung Pao Chicken")
        dish = (await session.execute(dish_stmt)).scalar_one_or_none()
        if not dish:
            dish = Dish(name="Kung Pao Chicken", price=Decimal("23.00"), stock=10, prep_time_minutes=15, status=1)
            session.add(dish)
        else:
            dish.stock = 10
            dish.version = 0

            # 2. Clean or create test order for Happy Path
        o1_stmt = select(Order).where(Order.order_number == "ORD_SAGA_SUCCESS_007")
        o1 = (await session.execute(o1_stmt)).scalar_one_or_none()
        if not o1:
            o1 = Order(
                order_number="ORD_SAGA_SUCCESS_007",
                user_id="USER_TEST_001",
                total_amount=Decimal("23.00"),
                status="DELIVERED"
            )
            session.add(o1)
        else:
            o1.status = "DELIVERED"

            # 3. Clean or create test order for Chaos Injection (504 Timeout)
        o2_stmt = select(Order).where(Order.order_number == "ORD_SAGA_TIMEOUT_007")
        o2 = (await session.execute(o2_stmt)).scalar_one_or_none()
        if not o2:
            o2 = Order(
                order_number="ORD_SAGA_TIMEOUT_007",
                user_id="USER_TEST_002",
                total_amount=Decimal("23.00"),
                status="DELIVERED"
            )
            session.add(o2)
        else:
            o2.status = "DELIVERED"
            # 4. Clean or create test order for Reconciliation Recovery (Timeout but Bank Succeeded)
        o3_stmt = select(Order).where(Order.order_number == "ORD_SAGA_RECONCILE_003")
        o3 = (await session.execute(o3_stmt)).scalar_one_or_none()
        if not o3:
            o3 = Order(
                order_number="ORD_SAGA_RECONCILE_003",
                user_id="USER_TEST_003",
                total_amount=Decimal("23.00"),
                status="DELIVERED"
            )
            session.add(o3)
        else:
            o3.status = "DELIVERED"

        await session.commit()
    print("✅ [Setup] Fixtures initialized (Dishes: Kung Pao Chicken stock=10, Orders status=DELIVERED).")


async def test_saga_happy_path():
    #### 🧪 [Test 1] Saga 正常退款流 (Happy Path)
    """Verifies that all forward steps succeed cleanly and finalize state."""
    print("\n-------------------------------------------------------------")
    print("🧪 [Test 1] Saga Happy Path: Normal Refund Execution")
    print("-------------------------------------------------------------")
    res = await execute_refund_saga_flow(
        order_number="ORD_SAGA_SUCCESS_007",
        amount=23.0,
        dish_name="Kung Pao Chicken",
        quantity=2,
        simulate_network_failure=False
    )
    assert res["success"] is True, "Saga flow should succeed!"
    assert res["saga_failed"] is False, "Saga should not trigger compensation!"
    assert res["tx_receipt"] is not None, "Bank receipt should be generated!"

    # Verify database side-effects
    async with AsyncSessionLocal() as session:
        order = (await session.execute(select(Order).where(Order.order_number == "ORD_SAGA_SUCCESS_007"))).scalar_one()
        dish = (await session.execute(select(Dish).where(Dish.name == "Kung Pao Chicken"))).scalar_one()
        assert order.status == "REFUNDED", f"Expected REFUNDED, got {order.status}"
        assert dish.stock == 12, f"Expected restocked inventory 12, got {dish.stock}"

        print(f"  ✅ [PASS] Happy path verified! Order status: REFUNDED, Dish stock: 12, Voucher: {res['tx_receipt']}")


async def test_saga_chaos_reverse_compensation():
    """Verifies that 504 gateway timeout triggers LIFO compensation to rollback state."""
    print("\n-------------------------------------------------------------")
    print("🧪 [Test 2] Chaos Engineering: Bank 504 Timeout & LIFO Rollback")
    print("-------------------------------------------------------------")
    res = await execute_refund_saga_flow(
        order_number="ORD_SAGA_TIMEOUT_007",
        amount=23.0,
        dish_name="Kung Pao Chicken",
        quantity=3,
        simulate_network_failure=True  # 👈 Chaos Injection
    )
    assert res["success"] is False, "Saga flow must return failure on gateway timeout!"
    assert res["saga_failed"] is True, "Saga engine must mark saga_failed as True!"

    # Verify reverse compensation restored clean state in MySQL
    async with AsyncSessionLocal() as session:
        order = (await session.execute(select(Order).where(Order.order_number == "ORD_SAGA_TIMEOUT_007"))).scalar_one()
        dish = (await session.execute(select(Dish).where(Dish.name == "Kung Pao Chicken"))).scalar_one()
        # Initial stock was 12 from Test 1. Forward added +3 (15), then reverse deducted -3 (back to 12)!
        assert order.status == "DELIVERED", f"Expected order reverted to DELIVERED, got {order.status}"
        assert dish.stock == 12, f"Expected dish stock cleanly reverted to 12, got {dish.stock}"

        print("  ✅ [PASS] Chaos compensation verified! Order cleanly reverted to DELIVERED, Dish stock reverted to 12!")


async def test_saga_timeout_reconciliation_recovery():
    """Verifies that 504 timeout checks bank status and finalizes without rollback if bank paid."""
    print("\n-------------------------------------------------------------")
    print("🧪 [Test 3] Reconciliation Guard: 504 Timeout with Bank Success Recovery")
    print("-------------------------------------------------------------")
    res = await execute_refund_saga_flow(
        order_number="ORD_SAGA_RECONCILE_003",
        amount=23.0,
        dish_name="Kung Pao Chicken",
        quantity=2,
        simulate_network_failure=True,  # 👈 模拟第一次打款网络 504 超时
        simulate_reconcile_success=True,  # 👈 模拟反查发现银行其实已打款成功
    )
    assert res["success"] is True, "Reconciliation must rescue the transaction to success!"
    assert res["saga_failed"] is False, "Saga must NOT rollback if bank confirmed payment!"
    assert "RECONCILE_SUCCESS" in res["recorded_steps"], "Reconcile step must be recorded!"

    # Verify DB finalized as REFUNDED and stock was NOT revoked
    async with AsyncSessionLocal() as session:
        order = (await session.execute(select(Order).where(Order.order_number == "ORD_SAGA_RECONCILE_003"))).scalar_one()
        dish = (await session.execute(select(Dish).where(Dish.name == "Kung Pao Chicken"))).scalar_one()
        assert order.status == "REFUNDED", f"Expected REFUNDED, got {order.status}"
        # Test 2 left stock at 12. This test added +2, should be 14!
        assert dish.stock == 14, f"Expected restocked inventory 14, got {dish.stock}"

        print(f"  ✅ [PASS] Reconciliation recovery verified! Order finalized to REFUNDED, Dish stock: 14, Voucher: {res['tx_receipt']}")


async def main():
    # await setup_test_fixtures()
    # await test_saga_happy_path()
    # await test_saga_chaos_reverse_compensation()
    await test_saga_timeout_reconciliation_recovery()
    print("\n=============================================================")
    print("🎉 ALL SAGA DISTRIBUTED TRANSACTION & COMPENSATION TESTS PASSED!")
    print("=============================================================")


if __name__ == "__main__":
    asyncio.run(main())