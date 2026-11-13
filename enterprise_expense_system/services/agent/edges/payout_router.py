from typing import Literal

from langgraph.constants import END
from loguru import logger

from schemas.state import ExpenseAuditState


# 扣预算操作 - 路由判断
def budget_router(state: ExpenseAuditState) -> Literal["transfer", "budget_failed_archive"]:
    if state.get("budget_deducted"):
        return "transfer"
    logger.error("部门预算扣减失败，中止打款并转入归档！")
    return "budget_failed_archive"


# 打款操作 - 路由判断
def transfer_router(state: ExpenseAuditState) -> Literal["failure_saga", "success"]:
    if state.get("bank_transfer_success"):
        return "success"
    return "failure_saga"