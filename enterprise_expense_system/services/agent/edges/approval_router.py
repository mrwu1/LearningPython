from typing import Literal

from loguru import logger

from schemas.state import ExpenseAuditState


def approval_router(state: ExpenseAuditState) -> Literal["payout", "rejected_archive"]:
    manager_decision = state.get("manager_decision") #{status:"approved",reason:""}
    logger.info(f"人工审核完成，结果：{manager_decision}")

    if manager_decision and manager_decision.get("status") == "approved":
        return "payout"
    else:
        return "rejected_archive"
