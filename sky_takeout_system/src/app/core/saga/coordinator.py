import asyncio
from loguru import logger

from app.core.saga.models import SagaContext, SagaStatus, SagaStep, AsyncStepAction, AsyncReconcileAction


class SagaCoordinator:
    """
    Enterprise Generic Saga Orchestrator:
    Executes ordered pipeline of forward steps, provides reconciliation self-healing on timeout,
    and guarantees eventual consistency via LIFO compensation with retry backoff and DLQ alerting.
    """

    def __init__(self, saga_name: str, max_retries: int = 3):
        self.saga_name: str = saga_name
        self.max_retries: int = max_retries
        self.steps: list[SagaStep] = []

    def add_step(
        self,
        name: str,
        forward: AsyncStepAction,
        compensate: AsyncStepAction = None,
        reconcile: AsyncReconcileAction = None,
    ) -> "SagaCoordinator":
        """Fluent builder API for assembling transaction steps."""
        self.steps.append(
            SagaStep(name=name, forward=forward, compensate=compensate, reconcile=reconcile)
        )
        return self

    async def run(self, context: SagaContext) -> SagaContext:
        """
        Executes the forward pipeline.
        Triggers reconciliation or LIFO compensation upon failure.
        """
        compensation_stack: list[SagaStep] = []
        logger.info(f"🚀 [Saga:{self.saga_name}] Starting pipeline ({context.tx_id}) with {len(self.steps)} steps.")

        for step in self.steps:
            try:
                logger.info(f"➡️ [Saga:{self.saga_name}] Executing forward step '{step.name}'...")
                # 1. Execute forward action
                await step.forward(context)
                context.record_step(step.name)

                # 2. Push to compensation stack if reverse callback exists
                if step.compensate:
                    compensation_stack.append(step)

            except Exception as exc:
                logger.warning(f"💥 [Saga:{self.saga_name}] Step '{step.name}' failed: {exc}")
                context.error = str(exc)

                # 3. Reconciliation Guard: Check if external system actually succeeded
                if step.reconcile:
                    logger.info(f"🔍 [Saga:{self.saga_name}] Invoking status reconciliation for '{step.name}'...")
                    reconcile_res = await step.reconcile(context)
                    if reconcile_res.get("status") == "SUCCESS":
                        logger.info(f"🎯 [Saga:{self.saga_name}] Reconciliation hit! Step '{step.name}' was actually processed.")
                        context.record_step(f"{step.name}_RECONCILED")
                        context.set("tx_receipt", reconcile_res.get("tx_receipt"))
                        continue  # Skip compensation, proceed forward!

                # 4. Trigger reverse compensation rollback
                context.status = SagaStatus.COMPENSATING
                await self._compensate(compensation_stack, context)
                return context

        # All steps succeeded
        context.status = SagaStatus.SUCCESS
        logger.info(f"🎉 [Saga:{self.saga_name}] Transaction {context.tx_id} completed successfully.")
        return context

    async def _compensate(self, compensation_stack: list[SagaStep], context: SagaContext) -> None:
        """Executes reverse compensation in LIFO order with exponential backoff retries."""
        logger.warning(
            f"🚨 [Saga:{self.saga_name}] Unwinding state: executing compensation for {len(compensation_stack)} steps..."
        )
        all_compensated = True

        while compensation_stack:
            step = compensation_stack.pop()
            compensated = False

            for attempt in range(1, self.max_retries + 1):
                try:
                    logger.warning(f"↩️ [Saga:{self.saga_name}] Compensating step '{step.name}' (Attempt {attempt}/{self.max_retries})...")
                    await step.compensate(context)
                    compensated = True
                    break
                except Exception as ce:
                    logger.warning(f"⚠️ [Saga:{self.saga_name}] Compensation on '{step.name}' attempt {attempt} failed: {ce}")
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.05 * (2 ** (attempt - 1)))

            if not compensated:
                all_compensated = False
                logger.critical(
                    f"🔥 [DLQ CRITICAL ALERT] Permanent compensation failure on step '{step.name}' "
                    f"in saga '{self.saga_name}' ({context.tx_id})! Escalated to manual DLQ reconciliation."
                )

        context.status = SagaStatus.COMPENSATED if all_compensated else SagaStatus.FAILED
        logger.info(f"🛡️ [Saga:{self.saga_name}] Compensation phase concluded. Final status: {context.status}")
