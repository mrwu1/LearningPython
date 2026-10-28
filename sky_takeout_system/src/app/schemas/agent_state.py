import operator
from typing import TypedDict, Annotated, Literal, List
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field


class DishStockReport(TypedDict):
    """Real-time kitchen inventory telemetry report."""
    dish_name: str
    in_stock: bool
    prep_time_minutes: int


class SkyTakeoutState(TypedDict):
    """
    Enterprise Global State for Sky Takeout Agent:
    Tracks conversation history, domain order IDs, dynamic human approvals, and stock reports.
    """
    # 链路追踪 ID (贯穿持久化快照与跨进程审计)
    trace_id: str

    # 核心对话上下文 (BSP add_messages 自动追加)
    messages: Annotated[list[BaseMessage], add_messages]

    # 业务会话身份
    order_id: str
    user_id: str
    dish_name: str  # Associated dish/SKU for orders and refunds

    # 拓扑路由指针 (强类型约束)
    next_worker: Literal["dish_advisor", "order_manager", "refund_officer", "FINISH"]

    # 菜品与冷库报告 (operator.add 汇聚动态并行检测)
    stock_reports: Annotated[list[DishStockReport], operator.add]

    # 售后退款与动态断点审批相关
    refund_amount: float
    refund_reason: str
    refund_status: str  # "NONE" | "PENDING_APPROVAL" | "APPROVED" | "REJECTED"
    reviewer_notes: str

   # 记录已执行的正向动作快照: [{"action": "LOCK_ORDER", ...}, {"action": "RESTOCK_DISH", ...}]
    saga_stack: List[str]
    saga_failed:bool # 是否触发了逆向回滚
    saga_error_msg:str  # 回滚原因 (如网关超时、余额不足) 

class SupervisorDecision(BaseModel):
    """
    Supervisor Structured Output Model (Pydantic V2):
    Used by DeepSeek / OpenAI function_calling to produce strict JSON schema decisions.
    """
    next_worker: Literal["dish_advisor", "order_manager", "refund_officer", "FINISH"] = Field(
        ...,
        description="The target specialist to route the customer request to."
    )
    reason: str = Field(
        ...,
        description="Reasoning behind selecting this worker."
    )
