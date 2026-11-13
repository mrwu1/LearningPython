
from fastapi import APIRouter, HTTPException, status
from langgraph.types import Command
from loguru import logger

from api.schemas import ExpenseWorkflowResponse, SubmitExpenseRequest
from schemas.invoice import ManagerDecision
from services.agent.graph.graph import expense_graph


# ✅：最后都需要把图当前的快照转换成统一的 ExpenseWorkflowResponse。
def _build_workflow_response(thread_id:str,config:dict)->ExpenseWorkflowResponse:
    """
    核心快照解析器：从 Checkpointer 读取 StateSnapshot，
    自动识别当前是处于 interrupt() 挂起态 (PENDING_APPROVAL) 还是已完结态 (COMPLETED)。
    """
    snap_shot = expense_graph.get_state(config=config)

    if not snap_shot or not snap_shot.values:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND
        )
    state_values = snap_shot.values
    next_nodes = list(snap_shot.next)
    is_pending = len(next_nodes)>0

    # 如果处于 interrupt() 挂起状态，从 snapshot.tasks 中提取中断抛出的上下文载荷
    interrupt_payload = None
    if is_pending and snap_shot.tasks:
        for task in snap_shot.tasks:
            if getattr(task,'interrupts',None):
                interrupt_payload = task.interrupts[0].value
                break
    return ExpenseWorkflowResponse(
        thread_id=thread_id,
        workflow_status="PENDING_APPROVAL" if is_pending else "COMPLETED",
        next_node=next_nodes,
        final_status= state_values.get("final_status"),
        risk_verdict=state_values.get("risk_verdict"),
        interrupt_payload=interrupt_payload,
        audit_trail=state_values.get("audit_trail", []),
    )

router = APIRouter(prefix="/api/v1/expenses", tags=["企业报销审计"])

@router.post(
    "/submit",
    response_model=ExpenseWorkflowResponse,
    status_code=status.HTTP_200_OK,
    summary="1. 员工提交报销单（自动触发初审、风控与出款/挂起）",
)
def submit_expense(req:SubmitExpenseRequest)->ExpenseWorkflowResponse:
    thread_id = req.invoice.invoice_id
    config = {
        "configurable":{
            "thread_id":thread_id,
        }
    }
    #幂等校验 - 如果历史记录中存在，则表示已经 提交过这条 审批了
    existing_snapshot = expense_graph.get_state(config=config)
    if existing_snapshot and existing_snapshot.values:
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail=f"发票 {thread_id} 已存在审批记录，请勿重复提交！可通过 GET /api/v1/expenses/{thread_id}查询进度。"
        )
    logger.info(f"📥 [API] 收到报销申请: thread_id={thread_id}, emp={req.invoice.employee_name},amount={req.invoice.amount}")

    initial_state={
        "invoice":req.invoice.model_dump(), ## 转回字典
        "simulate_bank_failure": req.simulate_bank_failure,
    }
    # 启动状态流转 - 提交
    expense_graph.invoke(
        initial_state,
        config=config,
    )
    return _build_workflow_response(thread_id,config)

# 主管 处理这条记录
@router.post(
    "/{thread_id}/approve",
    response_model=ExpenseWorkflowResponse,
    status_code=status.HTTP_200_OK,
    summary="2. 主管人工审批恢复（HITL 唤醒 interrupt 断点）",
)
def approve_expense(thread_id:str,decision:ManagerDecision)->ExpenseWorkflowResponse:
    # status: Literal["approved", "rejected"] = Field(..., description="审批动作: approved 或 rejected")
    # reason: str = Field(default="主管未填写具体意见", description="审批批注原因")
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = expense_graph.get_state(config=config)

    # 1.报销单必须存在
    if not snapshot or not snapshot.values:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到报销单: thread_id={thread_id}"
        )
    # 2. 节点必须停留在 human_approval
    if "human_approval" not in snapshot.next:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"报销单 {thread_id} 当前未处于待人工审批状态 (next={list(snapshot.next)},final_status = {snapshot.values.get('final_status')})，禁止重复或越权审批！"
        )
    logger.info(f"🔑 [API] 收到主管审批指令: thread_id={thread_id}, status={decision.status}, reason={decision.reason}")

    # 唤醒graph
    # 核心：使用 Command(resume=...) 将主管审批结果注入 human_approval_node 的 interrupt() 返回值，唤醒图继续执行
    expense_graph.invoke(
        Command(
            resume=decision.model_dump() # 转回字典
        ),
        config=config,
    )
    return _build_workflow_response(thread_id,config)

@router.get(
        "/{thread_id}",
        response_model=ExpenseWorkflowResponse,
        status_code=status.HTTP_200_OK,
        summary="3. 查询报销单当前状态与完整审计流水",
)
def get_expense_status(thread_id: str) -> ExpenseWorkflowResponse:
        config = {"configurable": {"thread_id": thread_id}}
        return _build_workflow_response(thread_id, config)