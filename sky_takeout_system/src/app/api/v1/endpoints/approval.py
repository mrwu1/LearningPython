from fastapi import APIRouter, Request, HTTPException, status, Depends
from langgraph.types import Command
from loguru import logger

from app.api.deps import require_role
from app.models import User
from app.schemas.takeout import TakeoutApproveRequest, TakeoutApproveResponse

router = APIRouter(prefix="/takeout", tags=["Takeout Agent Interactions"])


@router.post("/approve", response_model=TakeoutApproveResponse)
async def manager_approval_endpoint(
        payload: TakeoutApproveRequest,
        request: Request,
        current_manager: User = Depends(require_role("ROLE_STORE_MANAGER"))  # 👈 Enforces Manager Role Gate
):
    """
    Manager Human-in-the-Loop Resume Endpoint:
    Inspects PostgreSQL state snapshot for pending interrupts,
    and wakes up the graph via Command(resume=decision).
    """
    graph = request.app.state.graph
    thread_id = payload.session_id
    config = {"configurable": {"thread_id": thread_id}}

    # 1. 检查 PostgreSQL 持久化快照，验证是否真正处于挂起状态
    snapshot = await graph.aget_state(config)
    if not snapshot.tasks or not snapshot.tasks[0].interrupts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session '{thread_id}' is not currently paused at a review breakpoint."
        )

    logger.info(
        f"👨‍💼 [Manager Decision] Resuming session {thread_id} | "
        f"Decision: {payload.decision} | Amount: ${payload.approved_amount:.2f}"
    )

    # 2. 构造 resume 载荷唤醒图继续向下流转
    resume_payload = {
        "decision": payload.decision,
        "approved_amount": payload.approved_amount,
        # "notes": payload.notes
        "notes": f"[{current_manager.username}]: {payload.notes}"
    }
    result = await graph.ainvoke(Command(resume=resume_payload), config=config)

    latest_message = result["messages"][-1].content if result.get("messages") else "Operation processed."
    
    return TakeoutApproveResponse(
        status="RESUMED_SUCCESSFULLY",
        refund_status=result.get("refund_status", "UNKNOWN"),
        latest_reply=latest_message
    )
