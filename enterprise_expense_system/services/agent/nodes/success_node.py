from loguru import logger

from schemas.state import ExpenseAuditState

# ❌问题：当银行打款成功、整个分布式事务已经圆满提交（Commit）时：
# • 原来的代码没有清空
# compensation_stack（导致最终状态里还挂着['ROLLBACK_BUDGET']）；
# • 也没有往 audit_trail写入终态日志。

def success_node(state: ExpenseAuditState)->dict:
    logger.info("🎉 流程圆满完结，报销款已打入员工账户")
    return {
        "compensation_stack":[],#清空saga
        "final_status":"PAID_SUCCESS",
        "audit_trail":["流程圆满完结：银行打款到账，Saga 事务已提交 (PAID_SUCCESS)"]
    }