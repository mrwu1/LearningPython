import asyncio
from app.core.saga import SagaCoordinator, SagaContext, SagaStatus


async def test_generic_saga_happy_path():
    """Verifies all forward steps complete and status is SUCCESS."""
    print("\n[Case 1] Generic Saga: Happy Path Execution")

    async def step1_forward(ctx: SagaContext):
        ctx["stock"] = ctx.get("stock", 10) + 2

    async def step1_compensate(ctx: SagaContext):
        ctx["stock"] -= 2

    async def step2_forward(ctx: SagaContext):
        ctx["payout_done"] = True

    saga = (
        SagaCoordinator("GenericHappyPath")
        .add_step("RESTOCK", forward=step1_forward, compensate=step1_compensate)
        .add_step("PAYOUT", forward=step2_forward)
    )

    ctx = await saga.run(SagaContext(initial_data={"stock": 10}))
    assert ctx.status == SagaStatus.SUCCESS
    assert ctx["stock"] == 12
    assert ctx["payout_done"] is True
    print("  ✅ [PASS] Happy path successfully completed!")


async def test_generic_saga_compensation():
    """Verifies that an error in Step 2 triggers Step 1 reverse compensation."""
    print("\n[Case 2] Generic Saga: Step 2 Failure & LIFO Rollback")

    async def step1_forward(ctx: SagaContext):
        ctx["order_status"] = "REFUNDING"

    async def step1_compensate(ctx: SagaContext):
        ctx["order_status"] = "DELIVERED"

    async def step2_fail(ctx: SagaContext):
        raise ConnectionResetError("Third-party gateway dropped connection!")

    saga = (
        SagaCoordinator("GenericRollbackTest")
        .add_step("LOCK_ORDER", forward=step1_forward, compensate=step1_compensate)
        .add_step("BANK_PAYOUT", forward=step2_fail)
    )

    ctx = await saga.run(SagaContext(initial_data={"order_status": "DELIVERED"}))
    assert ctx.status == SagaStatus.COMPENSATED
    assert ctx["order_status"] == "DELIVERED"  # Verified reverted!
    print("  ✅ [PASS] LIFO compensation cleanly restored state!")


async def test_generic_saga_reconciliation_recovery():
    """Verifies that reconciliation recovers a timed out step without rollback."""
    print("\n[Case 3] Generic Saga: Timeout with Reconciliation Self-Healing")

    async def step1_forward(ctx: SagaContext):
        ctx["inventory"] = 20

    async def step1_compensate(ctx: SagaContext):
        ctx["inventory"] = 10

    async def step2_timeout(ctx: SagaContext):
        raise TimeoutError("504 Gateway Timeout")

    async def step2_reconcile(ctx: SagaContext):
        # Query bank and discover bank actually paid
        return {"status": "SUCCESS", "tx_receipt": "TX_RECONCILE_999"}

    saga = (
        SagaCoordinator("GenericReconcileTest")
        .add_step("INVENTORY", forward=step1_forward, compensate=step1_compensate)
        .add_step("NETWORK_CALL", forward=step2_timeout, reconcile=step2_reconcile)
    )

    ctx = await saga.run(SagaContext(initial_data={"inventory": 10}))
    assert ctx.status == SagaStatus.SUCCESS
    assert ctx["inventory"] == 20  # Verified not rolled back!
    assert ctx["tx_receipt"] == "TX_RECONCILE_999"
    print("  ✅ [PASS] Reconciliation self-healing successfully rescued transaction!")


async def main():
    await test_generic_saga_happy_path()
    await test_generic_saga_compensation()
    await test_generic_saga_reconciliation_recovery()
    print("\n=============================================================")
    print("🎉 ALL GENERIC SAGA FRAMEWORK UNIT TESTS PASSED!")
    print("=============================================================")


if __name__ == "__main__":
    asyncio.run(main())
