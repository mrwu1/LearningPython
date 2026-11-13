"""
================================================================================
【LangGraph 终极工业级大作业】苍穹外卖·多智能体协同履约与高并发流式中台
================================================================================
【核心综合架构与学习目标】：
本案例融合了从阶段一到阶段八的所有核心硬核技术：
1. 【多智能体主管协同 (Supervisor Pattern)】：
   - 中央总控主管（Supervisor）使用结构化输出（SupervisorDecision）进行精准意图路由分发；
   - 垂直专家矩阵：美食品鉴顾问（dish_advisor）、履约追踪调度（order_manager）、售后退款审核（refund_officer）。
2. 【人机协同与动态中断 (Human-in-the-Loop & interrupt)】：
   - 小额退款（<= $50）秒级自动到账；
   - 高额退款（> $50）触发动态挂起中断 `interrupt()`，向前端推送待审批事件，店长通过 `/approve` 接口唤醒恢复执行。
3. 【金融级工具幂等性与资金安全 (Tool Idempotency)】：
   - 引入幂等账本 `payout_idempotency_ledger`，彻底防止模型重试导致的重复扣款与资产流失。
4. 【会话级并发防抖互斥锁 (Session Mutex Lock)】：
   - 基于 `thread_id` 维护非阻塞并发锁，用户快速连击时直接返回 HTTP 429 保护系统免受竞态冲突。
5. 【企业级 FastAPI SSE 异步流式网关】：
   - 全异步架构，单例图编译生命周期（lifespan），集成 SSE 实时推送与客户端断开连接防护。
================================================================================
"""

import asyncio
import json
import operator
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
import random
from typing import TypedDict, Annotated, Literal, Dict

import httpx
import uvicorn
from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, Request, HTTPException
from sse_starlette import EventSourceResponse

# 保证本地模块与工具类正常导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END, START
from langgraph.types import interrupt, Command
from loguru import logger
from graph_utils import print_graph_mermaid

load_dotenv(find_dotenv())
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import add_messages, StateGraph
from pydantic import BaseModel, Field


# ==============================================================================
# 第一部分：状态契约定义（State Schemas）
# ==============================================================================

# 基础菜品结构
class DishItem(TypedDict):
    dish_id: str
    dish_name: str
    quantity: int


# 单菜品库存质检报告
class DishStockReport(TypedDict):
    dish_name: str
    in_stock: bool
    prep_time_minutes: int


# 【全局主状态（SkyTakeoutState）】：多智能体与流程共享的顶层状态
class SkyTakeoutState(TypedDict):
    order_id: str
    user_id: str

    # 对话消息流（使用 add_messages 自动去重追加）
    messages: Annotated[list[BaseMessage], add_messages]

    # 下一个等待执行的专员或终结标记 ("dish_advisor" | "order_manager" | "refund_officer" | "FINISH")
    next_worker: str

    # 订单相关字段与并行质检报告通道（挂载 operator.add 汇聚并发报告）
    order_items: list[DishItem]
    stock_reports: Annotated[list[DishStockReport], operator.add]

    # 售后退款与人机协同相关字段
    refund_amount: float
    refund_reason: str
    refund_status: str       # "NONE" | "PENDING_APPROVAL" | "APPROVED" | "REJECTED"
    reviewer_notes: str      # 店长审批批注

    fulfillment_disposition: str  # 履约综合处置结论


# 主控主管（Supervisor）的结构化决策模型
class SupervisorDecision(BaseModel):
    next_worker: Literal["dish_advisor", "order_manager", "refund_officer", "FINISH"] = Field(
        ...,
        description="下一步指派处理用户诉求的专员角色，若已满足则为 FINISH。"
    )
    reason: str = Field(..., description="选择指派该角色的核心业务研判理由。")


# ==============================================================================
# 第二部分：基础设施与金融级受保护工具（Tools & Storage）
# ==============================================================================

# 模拟商户结算资金钱包（初始储备金 $500.00）
merchant_wallet = {"balance": 500.00}

# 模拟后厨仓储数据库
warehouse_db = {
    "Wagyu_Steak": {"stock": 8, "prep_time": 15},
    "Salmon_Salad": {"stock": 12, "prep_time": 8},
    "Mushroom_Soup": {"stock": 5, "prep_time": 6}
}

# 幂等防重放账本：记录已经完成退款的 order_id 与凭证，防止资金重复流失
payout_idempotency_ledger: Dict[str, dict] = {}


@tool
def execute_refund_payout(order_id: str, amount: float) -> str:
    """
    【受幂等保护的退款打款工具】：
    1. 查阅幂等账本：若 order_id 已存在，直接拦截，返回已退款收据，绝不二次扣费；
    2. 若不存在：扣减商户账户余额，登记到账本，返回银行划账凭证。
    """
    if payout_idempotency_ledger.get(order_id):
        logger.warning(f"🛡️ [幂等拦截] 订单 {order_id} 此前已退款，直接返回历史收据，拦截重复扣费！")
        return f"[幂等缓存命中] 订单 {order_id} 历史已完成退款: ${amount:,.2f}"
    
    merchant_wallet["balance"] -= amount
    payout_idempotency_ledger[order_id] = {"amount": amount, "status": "SETTLED"}
    logger.info(f"💰 [财务打款] 订单 {order_id} 成功退款 ${amount:,.2f}。商户余额: ${merchant_wallet['balance']:,.2f}")
    return f"[退款成功] 订单 {order_id} 划扣完成，实退: ${amount:,.2f}，流水已记账。"


@tool
def query_courier_telemetry(order_id: str) -> str:
    """【骑手雷达定位工具】：模拟连接北斗/GPS IoT 卫星接口获取骑手时空轨迹。"""
    return "骑手【王师傅】距离您约 850 米，正以 25 km/h 速度行驶，预计 6 分钟送达。"


def inspect_single_dish_stock(dish_name: str, quantity: int) -> DishStockReport:
    """【单菜品库存与耗时核验】：供动态 Map-Reduce 算子调用。"""
    in_stock = False
    dish_meta = warehouse_db.get(dish_name)
    if dish_meta and dish_meta["stock"] >= quantity:
        in_stock = True
    
    return {
        "dish_name": dish_name,
        "in_stock": in_stock,
        "prep_time_minutes": random.randint(10, 20)
    }


def get_llm():
    """获取统一的大语言模型单例（温度为 0 确保高确定性）。"""
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.0
    )


# ==============================================================================
# 第三部分：垂直专家智能体节点（Specialist Workers）
# ==============================================================================

def dish_advisor_worker(state: SkyTakeoutState) -> dict:
    """【专家 1：美食品鉴顾问】：解答菜品热量、口味与营养膳食搭配。"""
    llm = get_llm()
    system_prompt = (
        "你是苍穹外卖的高级美食品鉴顾问。\n"
        "你精通营养搭配与健康美味餐品组合，请以热情专业的口吻在2句话内为顾客提供美味推荐。"
    )
    response = llm.invoke([SystemMessage(content=system_prompt)] + state["messages"])
    return {
        "messages": [AIMessage(content=f"【美食品鉴专家】: {response.content}")],
        "next_worker": "FINISH"
    }


def order_manager_worker(state: SkyTakeoutState) -> dict:
    """【专家 2：履约调度管家】：调用物流遥测工具，向顾客播报骑手实时位置。"""
    order_id = state.get("order_id", "ORD-UNKNOWN")
    telemetry = query_courier_telemetry.invoke({"order_id": order_id})

    llm = get_llm()
    prompt = [
        SystemMessage(
            content=f"你是苍穹外卖的物流调度经理。最新调度雷达数据: '{telemetry}'。\n"
                    f"请以礼貌安抚的口吻，在2句话内告知顾客最新送餐进展。"
        ),
        HumanMessage(content=state["messages"][-1].content)
    ]
    response = llm.invoke(prompt)
    return {
        "messages": [AIMessage(content=f"【履约调度专家】: {response.content}")],
        "next_worker": "FINISH"
    }


def refund_officer_worker(state: SkyTakeoutState) -> dict:
    """
    【专家 3：售后退款仲裁员（含人机协同动态中断）】：
    - 状态守卫：若订单退款已终结，快速退出，杜绝死循环；
    - 规则 1：退款金额 <= $50 -> 极速秒退（自动放款）；
    - 规则 2：退款金额 > $50 -> 触发动态挂起中断 `interrupt()`，等待店长审批！
    """
    # 状态守卫
    if state.get("refund_status") in ["APPROVED", "REJECTED"]:
        logger.info(f"[售后专员] 退款已处于终态 ({state['refund_status']})，直接结束。")
        return {"next_worker": "FINISH"}

    amount = state.get("refund_amount", 0.0)
    order_id = state.get("order_id", "UNKNOWN")

    # 规则 1：小额快速放款
    if amount <= 50.0:
        receipt = execute_refund_payout.invoke({"order_id": order_id, "amount": amount})
        return {
            "refund_amount": amount,
            "refund_status": "APPROVED",
            "messages": [AIMessage(content=f"【售后专员】: 小额极速通道已为您自动退款：{receipt}")],
            "next_worker": "FINISH"
        }

    # 规则 2：高额人工审批中断挂起
    print(f"\n⏸️ [动态中断] 订单 {order_id} 申请退款 ${amount:,.2f} > $50，系统挂起并等待店长审批...")
    admin_approval = interrupt({
        "alert": "HIGH_VALUE_REFUND_ALERT",
        "order_id": state["order_id"],
        "amount": amount,
        "reason": state.get("refund_reason", "顾客投诉餐品冷")
    })

    # 当外界通过 Command(resume=decision) 唤醒图时，代码从本行无缝恢复继续执行！
    print(f"🚀 [图被唤醒] 收到店长审批决策: {admin_approval}")
    if admin_approval.get("decision") == "APPROVED":
        real_refund_amount = admin_approval.get("approved_amount", amount)
        receipt = execute_refund_payout.invoke({"order_id": order_id, "amount": real_refund_amount})
        return {
            "refund_status": "APPROVED",
            "reviewer_notes": admin_approval.get("notes", "店长审批通过"),
            "messages": [AIMessage(content=f"【售后专员】: 店长审批通过，款项已退回您的账户：{receipt}")],
            "next_worker": "FINISH"
        }
    else:
        return {
            "refund_status": "REJECTED",
            "reviewer_notes": admin_approval.get("notes", "店长驳回退款"),
            "messages": [AIMessage(content="【售后专员】: 经后厨与店长核查，您的退款申请已被驳回。")],
            "next_worker": "FINISH"
        }


# ==============================================================================
# 第四部分：主控调度主管与拓扑编排（Supervisor Pipeline）
# ==============================================================================

def supervisor_node(state: SkyTakeoutState) -> dict:
    """
    【总控调度主管节点】：
    - 防御层：终态短路检查，若已解决直接返回 FINISH，0 延迟、0 Token 开销；
    - 认知层：通过 Function Calling 结构化输出准确指派责任专员。
    """
    current_status = state.get("refund_status", "NONE")
    # 代码级终态短路
    if current_status in ["APPROVED", "REJECTED"]:
        logger.info(f"🛡️ [主管防御守卫] 订单已处理完毕 ({current_status})，绕过大模型直接终结退出。")
        return {"next_worker": "FINISH"}

    supervisor_prompt = (
        "你是苍穹外卖多智能体协同中台的中央总控调度官（Supervisor）。\n"
        "请依据顾客的最新输入，将任务准确指派给最合适的专业人员：\n"
        "=== 系统实时状态 ===\n"
        f"- 关联订单号: {state.get('order_id', 'N/A')}\n"
        f"- 当前退款状态: {current_status}\n"
        f"- 申请退款金额: ${state.get('refund_amount', 0.0):.2f}\n"
        "====================\n\n"
        "候选专家列表:\n"
        "  1. 'dish_advisor'  : 负责菜品推荐、减脂搭配、热量营养、口味建议。\n"
        "  2. 'order_manager' : 负责送达时间追踪、骑手实时位置定位、催单配送。\n"
        "  3. 'refund_officer': 负责售后退款、餐品洒漏/变冷赔付、取消订单退费。\n"
        "  4. 'FINISH'        : 如果问题已圆满回答，或是日常问候，选择 FINISH。"
    )
    llm = get_llm()
    structured_llm = llm.with_structured_output(SupervisorDecision, method="function_calling")
    decision: SupervisorDecision = structured_llm.invoke(
        [SystemMessage(content=supervisor_prompt)] + state["messages"]
    )
    logger.info(f"🎯 [主管指派] -> '{decision.next_worker}' | 原因: {decision.reason}")
    return {"next_worker": decision.next_worker}


def route_from_supervisor(state: SkyTakeoutState) -> Literal["dish_advisor", "order_manager", "refund_officer", END]:
    target = state.get("next_worker", "FINISH")
    if target == "FINISH" or not target:
        return END
    return target


def build_sky_takeout_graph():
    """组装并编译苍穹外卖全功能状态机图。"""
    builder = StateGraph(SkyTakeoutState)

    # 注册主管与三位专家节点
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("dish_advisor", dish_advisor_worker)
    builder.add_node("order_manager", order_manager_worker)
    builder.add_node("refund_officer", refund_officer_worker)

    # 起点连接主管
    builder.add_edge(START, "supervisor")

    # 主管进行动态条件分发
    builder.add_conditional_edges("supervisor", route_from_supervisor)

    # 专家完成业务后，环形闭环回传主管做统一质检与终结确认
    builder.add_edge("dish_advisor", "supervisor")
    builder.add_edge("order_manager", "supervisor")
    builder.add_edge("refund_officer", "supervisor")

    return builder.compile(checkpointer=MemorySaver())


# ==============================================================================
# 第五部分：高并发互斥锁与 FastAPI 网关中台
# ==============================================================================

class AsyncSessionLockManager:
    """会话互斥并发锁管理器：防止同一 session 快速双击产生竞态脏数据。"""
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def acquire(self, thread_id: str) -> bool:
        async with self._guard:
            if thread_id not in self._locks:
                self._locks[thread_id] = asyncio.Lock()
        lock = self._locks[thread_id]
        if lock.locked():
            return False  # 已被占用
        await lock.acquire()
        return True

    def release(self, thread_id: str):
        if thread_id in self._locks and self._locks[thread_id].locked():
            self._locks[thread_id].release()


class TakeoutChatRequest(BaseModel):
    session_id: str = Field(..., description="用户唯一会话 thread_id")
    user_id: str = Field(default="USER_001")
    order_id: str = Field(default="ORD-001")
    query: str = Field(..., description="用户咨询提问内容")
    refund_amount: float = Field(default=0.0)
    refund_reason: str = Field(default="")


class TakeoutApproveRequest(BaseModel):
    session_id: str = Field(..., description="处于挂起中断中的目标 thread_id")
    decision: Literal["APPROVED", "REJECTED"] = Field(...)
    approved_amount: float = Field(default=0.0)
    notes: str = Field(default="店长已完成审批")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 [网关生命周期] 正在预编译苍穹外卖图单例引擎并就绪并发锁...")
    app.state.graph = build_sky_takeout_graph()
    app.state.lock_manager = AsyncSessionLockManager()
    logger.info("✅ [网关生命周期] 图引擎与锁管理器初始化就绪。")
    yield
    logger.info("🛑 [网关生命周期] 网关正常安全关闭。")


api_app = FastAPI(title="苍穹外卖多智能体高并发中台", lifespan=lifespan)


@api_app.post("/api/v1/takeout/chat")
async def chat_stream_endpoint(payload: TakeoutChatRequest, request: Request):
    """顾客多轮对话与流式推理端点（集成并发锁与动态中断探测）。"""
    lock_mgr: AsyncSessionLockManager = request.app.state.lock_manager
    graph = request.app.state.graph
    thread_id = payload.session_id

    # 1. 获取会话锁，如果冲突直接报 HTTP 429
    if not await lock_mgr.acquire(thread_id):
        raise HTTPException(status_code=429, detail=f"会话 {thread_id} 正在处理中，请勿重复频繁点击！")

    config = {"configurable": {"thread_id": thread_id}}
    initial_input = {
        "messages": [HumanMessage(content=payload.query)],
        "order_id": payload.order_id,
        "user_id": payload.user_id,
        "next_worker": "",
        "order_items": [],
        "stock_reports": [],
        "refund_amount": payload.refund_amount,
        "refund_reason": payload.refund_reason,
        "refund_status": "NONE",
        "reviewer_notes": "",
        "fulfillment_disposition": ""
    }

    async def sse_generator():
        try:
            async for mode, event in graph.astream(initial_input, stream_mode=["updates"], config=config):
                if await request.is_disconnected():
                    logger.warning(f"客户端断开连接，终止流生成: {thread_id}")
                    break
                # 推送超步节点更新事件
                yield {"event": "node_update", "data": json.dumps(list(event.keys()))}

            # 检查当前图是否停在动态中断挂起点
            snapshot = graph.get_state(config)
            if snapshot.tasks and snapshot.tasks[0].interrupts:
                alert = snapshot.tasks[0].interrupts[0].value
                yield {
                    "event": "human_approval_required",
                    "data": json.dumps({"alert": alert, "session_id": thread_id})
                }
            else:
                yield {"event": "done", "data": "[DONE]"}
        finally:
            lock_mgr.release(thread_id)

    return EventSourceResponse(sse_generator())


@api_app.post("/api/v1/takeout/approve")
async def manager_approve_endpoint(payload: TakeoutApproveRequest, request: Request):
    """店长人工审批唤醒端点（利用 Command(resume=...) 唤醒挂起中的图）。"""
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": payload.session_id}}
    snapshot = graph.get_state(config)

    if not snapshot.tasks or not snapshot.tasks[0].interrupts:
        raise HTTPException(status_code=400, detail="目标会话并不处于挂起中断状态，无法审批！")

    # 使用 Command(resume=...) 唤醒图！
    resume_payload = {
        "decision": payload.decision,
        "approved_amount": payload.approved_amount,
        "notes": payload.notes
    }
    result = await graph.ainvoke(Command(resume=resume_payload), config=config)
    return {
        "status": "RESUMED_SUCCESSFULLY",
        "refund_status": result.get("refund_status"),
        "latest_reply": result["messages"][-1].content,
        "merchant_wallet_balance": merchant_wallet["balance"]
    }


# ==============================================================================
# 第六部分：全真端到端 HTTP & SSE 模拟沙盒（E2E Verification Sandbox）
# ==============================================================================
async def run_full_api_simulation():
    """在后台拉起 Uvicorn 服务，全面测试 SSE 流、并发防抖与店长审批恢复三条链路。"""
    server_port = 8099
    server_config = uvicorn.Config(api_app, host="127.0.0.1", port=server_port, log_level="warning")
    server = uvicorn.Server(server_config)
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.8)  # 等待服务就绪

    base_url = f"http://127.0.0.1:{server_port}"
    logger.info(f"🌐 [E2E 测试] FastAPI 测试服务已启动于 {base_url}")

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            # -----------------------------------------------------------------
            # 测试用例 1：顾客普通点餐咨询 -> 验证 SSE 节点推进流
            # -----------------------------------------------------------------
            print("\n" + "=" * 70)
            print(" 🧪 【测试用例 1】：SSE 流式顾客点餐咨询测试")
            print("=" * 70)
            chat_payload = {
                "session_id": "CLIENT_SESSION_ADVICE_01",
                "order_id": "ORD-001",
                "query": "请推荐一份 500 大卡以内的优质高蛋白三文鱼餐食。"
            }
            async with client.stream("POST", "/api/v1/takeout/chat", json=chat_payload) as resp:
                print(f"HTTP 状态码: {resp.status_code} | Content-Type: {resp.headers.get('content-type')}")
                current_event = None
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("event: "):
                        current_event = line.replace("event: ", "").strip()
                    elif line.startswith("data: "):
                        raw_data = line.replace("data: ", "").strip()
                        print(f"  [SSE 实时事件: {current_event}] -> {raw_data}")

            # -----------------------------------------------------------------
            # 测试用例 2：会话并发锁防抖测试 -> 模拟双击快速连击，验证触发 HTTP 429
            # -----------------------------------------------------------------
            print("\n" + "=" * 70)
            print(" 🧪 【测试用例 2】：会话互斥并发锁防抖测试 (模拟快速双击)")
            print("=" * 70)
            busy_payload = {
                "session_id": "RAPID_CLICK_SESSION_02",
                "order_id": "ORD-002",
                "query": "我的外卖现在到哪里了？"
            }

            async def send_chat_req():
                return await client.post("/api/v1/takeout/chat", json=busy_payload)

            req_a, req_b = await asyncio.gather(send_chat_req(), send_chat_req(), return_exceptions=True)
            statuses = [getattr(r, "status_code", "ERROR") for r in [req_a, req_b]]
            print(f"并发请求状态码汇总: {statuses}")
            if 429 in statuses:
                print("  ✅ [验证成功] 互斥并发锁精准生效！拦截连击并返回 HTTP 429！")

            # -----------------------------------------------------------------
            # 测试用例 3：大额退款 ($120) 动态中断挂起告警 + 店长后台审批唤醒
            # -----------------------------------------------------------------
            print("\n" + "=" * 70)
            print(" 🧪 【测试用例 3】：$120 大额退款中断告警与店长审批恢复全链路")
            print("=" * 70)
            refund_session_id = "REFUND_HTTP_SESSION_03"
            refund_payload = {
                "session_id": refund_session_id,
                "order_id": "ORD-TAKEOUT-9903",
                "query": "送来的10份牛排完全是冰凉变质的！要求立即全额退款 $120 元！",
                "refund_amount": 120.0,
                "refund_reason": "牛排严重冰凉变质"
            }

            # 步骤 3.1: 顾客发起退款申请，流式接收挂起告警
            async with client.stream("POST", "/api/v1/takeout/chat", json=refund_payload) as resp:
                current_event = None
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("event: "):
                        current_event = line.replace("event: ", "").strip()
                    elif line.startswith("data: "):
                        raw_data = line.replace("data: ", "").strip()
                        if current_event == "human_approval_required":
                            print(f"  🚨 [收到动态中断审批挂起告警]:\n     {raw_data}")

            # 步骤 3.2: 模拟店长在管理端审查并点击“核减代金券，准予退款 $100”
            print("\n  👉 店长在后台核验送餐记录，调用 /approve 接口执行批准恢复...")
            approve_payload = {
                "session_id": refund_session_id,
                "decision": "APPROVED",
                "approved_amount": 100.0,
                "notes": "与骑手核实配送确实超时且餐品冰冷，扣除配送费后同意退款 $100 元。"
            }
            approve_resp = await client.post("/api/v1/takeout/approve", json=approve_payload)
            print(f"  审批响应状态码: {approve_resp.status_code}")
            print(f"  审批响应详情:\n  {json.dumps(approve_resp.json(), indent=4, ensure_ascii=False)}")

    finally:
        print("\n" + "=" * 70)
        print(" 🏁 苍穹外卖中台全真演练圆满完成，正在关闭测试服务...")
        print("=" * 70)
        server.should_exit = True
        await server_task


if __name__ == "__main__":
    asyncio.run(run_full_api_simulation())
