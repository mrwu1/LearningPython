from typing import Literal, Optional
from pydantic import BaseModel, Field


class TakeoutChatRequest(BaseModel):
    """Customer chat and takeout inquiry payload."""
    session_id: str = Field(..., description="Unique thread_id for conversation persistence in PostgreSQL")
    user_id: str = Field(default="USER_001", description="Customer identity identifier")
    order_id: str = Field(default="ORD-TAKEOUT-9901", description="Associated domain order number")
    query: str = Field(..., description="Customer natural language message")
    refund_amount: float = Field(default=0.0, description="Refund claim amount if applicable")
    refund_reason: str = Field(default="", description="Reason for refund complaint")


class TakeoutApproveRequest(BaseModel):
    """Manager human-in-the-loop review decision payload."""
    session_id: str = Field(..., description="Target thread_id paused at interrupt()")
    decision: Literal["APPROVED", "REJECTED"] = Field(..., description="Manager approval verdict")
    approved_amount: float = Field(default=0.0, description="Adjusted / finalized payout amount")
    notes: str = Field(default="Manager review completed", description="Reviewer audit explanation")


class TakeoutApproveResponse(BaseModel):
    """Response returned upon waking up a paused interrupt graph."""
    status: str
    refund_status: str
    latest_reply: str
    tx_receipt: Optional[str] = None


class HealthCheckResponse(BaseModel):
    """Comprehensive readiness probe for K8s infrastructure checks."""
    status: str
    mysql: bool
    redis: bool
    postgres: bool
    app_name: str
