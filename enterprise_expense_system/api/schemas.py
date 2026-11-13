from typing import Literal, Any

from pydantic import BaseModel, Field

from schemas.invoice import InvoiceItem

# 因为前端需要明确知道：
#
# 1.
# 这笔报销单的工作流当前处于什么生命周期（workflow_status：是
# PENDING_APPROVAL
# 挂起待审，还是
# COMPLETED
# 已完结？）；
# 2.
# 会话追踪号
# thread_id
# 是多少（后续主管审批要传这个
# ID）；
# 3.如果被interrupt()挂起了，中断抛出来的待审详情
# interrupt_payload
# 是什么。

# request
class SubmitExpenseRequest(BaseModel):
    """员工提交报销单的http请求体"""
    invoice:InvoiceItem = Field(...,description="报销发票详情")
    simulate_bank_failure:bool = Field(
        default=False,
        description="沙盒演练开关：是否模拟银行打款网关 500 故障（用于测试 Saga 回滚）"
    )

# response
class ExpenseWorkflowResponse(BaseModel):
    """统一的报销工作流 http响应体"""
    thread_id: str = Field(..., description="LangGraph 状态机持久化追踪 ID (默认与 invoice_id 一致)")
    workflow_status:Literal["PENDING_APPROVAL","COMPLETED"] = Field(
        description="图运行状态：PENDING_APPROVAL(挂起等待主管特批) / COMPLETED(已抵达终态)"
    )
    next_node: list[str] = Field(default_factory=list, description="当前挂起等待执行的节点列表")
    final_status: str | None = Field(
        default=None,
        description="业务终态：PAID_SUCCESS / REJECTED_BY_RISK_CONTROL / REJECTED_BY_MANAGER / ABORTED_INSUFFICIENT_BUDGET / PAYOUT_FAILED_COMPENSATED "
    )
    risk_verdict: str | None = Field(default=None, description="风控裁决结论")
    interrupt_payload: dict[str, Any] | None = Field(
        default=None,
        description="当 workflow_status 为 PENDING_APPROVAL 时，提供给主管审批后台的上下文载荷"
    )
    audit_trail: list[str] = Field(default_factory=list, description="完整不可篡改的审计流水日志")


