from typing import Literal

from langgraph.constants import END
from loguru import logger

from schemas.state import ExpenseAuditState


def risk_router(state: ExpenseAuditState) -> Literal["back_archive", "human_approval", "payout"]:
    risk_verdict = state.get("risk_verdict", "")
    logger.info(f"风险评估结束：进行路由定向 {risk_verdict}")
    if risk_verdict == "AUTO_APPROVED":
        return "payout"
    elif risk_verdict == "REJECTED":
        return "back_archive"
    else:
        return "human_approval"
