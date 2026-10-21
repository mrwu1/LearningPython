import asyncio
import json
import operator
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
import random
from pprint import pprint
from typing import TypedDict, Annotated, Literal, Dict

import httpx
import uvicorn
from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, Request, HTTPException
from sse_starlette import EventSourceResponse

# Standard sys.path setup must come BEFORE local imports
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

# Standard sys.path setup
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

class DishItem(TypedDict):
    dish_id:str
    dish_name:str
    quantity:int

class DishStockReport(TypedDict):
    dish_name:str
    in_stock:bool
    prep_time_minutes:int

# 1. global state
class SkyTakeoutState(TypedDict):
    order_id:str
    user_id:str

    messages:Annotated[list[BaseMessage],add_messages]

    #  ("dish_advisor" | "order_manager" | "refund_officer" | "FINISH")
    next_worker:str

    order_items:list[DishItem]
    stock_reports:Annotated[list[DishStockReport],operator.add] # 必须用 operator.add 汇聚并发！

    # 售后退款与动态断点审批相关
    refund_amount:float
    refund_reason:str
    refund_status:str # "NONE" | "PENDING_APPROVAL" | "APPROVED" | "REJECTED"
    reviewer_notes:str

    fulfillment_disposition:str

# the super brain
class SupervisorDecision(BaseModel):
    next_worker:Literal["dish_advisor", "order_manager", "refund_officer", "FINISH"] = Field(...,description="next worker")
    reason:str = Field(...,description='the reason why move the target node!')

# user
merchant_wallet = {"balance": 500.00}
# db
warehouse_db = {
    "Wagyu_Steak": {"stock": 8, "prep_time": 15},
    "Salmon_Salad": {"stock": 12, "prep_time": 8},
    "Mushroom_Soup": {"stock": 5, "prep_time": 6}
}
# 3. 幂等性防重放账本 (记录已经成功退款的 order_id 和收据)
payout_idempotency_ledger: Dict[str, dict] = {}

@tool
def execute_refund_payout(order_id:str,amount:float)->str:
    # 逻辑：
    # 1. 先查 payout_idempotency_ledger，如果 order_id 已存在：
    #    logger.warning("触发幂等拦截！返回缓存凭据")，绝不重复扣钱！
    # 2. 如果不存在：扣减 merchant_wallet['balance']，记录到账本，返回成功收据
    """verify the order_id whether been recorded"""
    if payout_idempotency_ledger.get(order_id):
        logger.warning("触发幂等拦截！返回缓存凭据")
        return f"the order_id {order_id} is already exist:{amount}"
    else:
        merchant_wallet["balance"] = merchant_wallet["balance"] - amount
        payout_idempotency_ledger[order_id] = amount
        return f"this order_id:{order_id} has been recorded in the system"

@tool
def query_courier_telemetry(order_id:str)->str:
    # 逻辑：模拟调用高德/IoT 卫星接口
    #接收 order_id，模拟返回骑手姓名、距离当前位置的公里数以及预计送达分钟数（ETA）。
    """return the rider name,distance and arrive time"""
    return "Courier Xiao Wang is 850m away, traveling at 25km/h, ETA: 6 mins."

def inspect_single_dish_stock(dish_name: str, quantity: int)->DishStockReport:
    #模拟后厨冷库，输入菜品名称与数量，返回是否缺货以及备餐时长。
    # 逻辑：查 warehouse_db，如果存在且 stock >= quantity，则 in_stock=True
    # 工具 1：单菜品库存与备餐时间核验 (供后续 Send API 动态并发调用)
    """菜品库存与备餐时间核验"""
    in_stock:bool = False
    stock = warehouse_db.get(dish_name)["stock"]
    if stock and stock >= quantity:
        in_stock = True
    dish_stock_report:DishStockReport = {
        "dish_name": dish_name,
        "in_stock": in_stock,
        "prep_time_minutes": random.randint(10,100)
    }
    return dish_stock_report
def get_llm():
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.0
    )
# 2. worker
# ✅✅✅ - llm
def dish_advisor_worker(state:SkyTakeoutState):
    # 调用 LLM 给出热情推荐...
    # 如果用户传了 order_items，后续通过条件边 dispatch_dish_stock_checks 返回 [Send("stock_worker", item)...]
    """Specialist 1: Recommends delicious, healthy meals."""
    llm = get_llm()
    system_prompt = (
        "You are the Sky Takeout Gourmet Advisor. You specialize in meal pairing and healthy diet recommendations. "
        "Answer the customer's food request warmly in 2 concise sentences."
    )
    response = llm.invoke([SystemMessage(content=system_prompt)] + state["messages"])

    return {
        "messages": [AIMessage(content=f"[Dish Advisor]: {response.content}")],
        "next_worker": "FINISH"
    }


# worker - stock
def stock_worker_node(state:dict):
    # 单个 worker 调用我们刚才写好的 inspect_single_dish_stock！
    report = inspect_single_dish_stock(state["item"]["dish_name"], state["item"]["quantity"])
    return {"stock_reports":[report]}
# worker - refund
def refund_officer_worker(state:SkyTakeoutState):
    # 状态守卫：如果退款已处理完毕（APPROVED 或 REJECTED），直接退出，杜绝死循环
    if state.get("refund_status") in ["APPROVED", "REJECTED"]:
        logger.info(f"[Supervisor] Refund already finalized ({state['refund_status']}) -> 'FINISH'")
        return {"next_worker": "FINISH"}

    amount = state.get("refund_amount", 0.0)
    order_id = state.get("order_id", "UNKNOWN")
    # 规则 1：<= 50 元小额，极速自动退款！
    if amount <= 50:
        receipt = execute_refund_payout.invoke({"order_id": order_id, "amount": amount})
        return {
            "refund_amount": amount,
            "refund_status":"APPROVED",
            "messages":[AIMessage(content=f"[Refund Officer]: 小额退款已秒级完成打款：{receipt}")],
            "next_worker":"FINISH"
       }
    # 规则 2：> 50 元大额高危，触发动态断点挂起！
    else:
        admin_approval = interrupt(
            {
                "alert": "HIGH_VALUE_REFUND_ALERT",
                "order_id": state["order_id"],
                "amount": amount,
                "reason": state.get("refund_reason", "顾客投诉")
            }
        )
    # 当外界通过 Command(resume=decision) 唤醒时，代码直接从这里苏醒继续执行！
    if admin_approval.get("decision")=="APPROVED":
        real_refund_amount = admin_approval.get("approved_amount",
                                                admin_approval.get("approval_amount", amount))
        receipt = execute_refund_payout.invoke(
            {"order_id": order_id, "amount": real_refund_amount}
        )
        return {
            "refund_status": "APPROVED",
            "reviewer_notes": admin_approval.get("notes", "店长审批通过"),
            "messages": [AIMessage(content=f"[Refund Officer]: 店长审批通过，退款成功：{receipt}")],
            "next_worker": "FINISH"
        }
    else:
        return {
            "refund_status": "REJECTED",
            "reviewer_notes": admin_approval.get("notes", "店长驳回"),
            "messages": [AIMessage(content="[Refund Officer]: 经店长核验，您的退款申请已被驳回。")],
            "next_worker": "FINISH"
        }

# ✅✅✅ - llm
def order_manager_worker(state: SkyTakeoutState):
        """Specialist 2: Queries real-time courier telemetry and reassures customer."""
        order_id = state.get("order_id", "ORD-UNKNOWN")
        # 调用我们的工具 2 获取真实物流状态
        telemetry = query_courier_telemetry.invoke({"order_id": order_id})

        llm = get_llm()
        prompt = [
            SystemMessage(
                content=f"You are the Sky Takeout Logistics Manager. Courier telemetry: '{telemetry}'. "
                        f"Reassurecustomer in 2 sentences."), HumanMessage(content=state["messages"][-1].content)
        ]
        response = llm.invoke(prompt)
        return {
            "messages": [AIMessage(content=f"[Order Manager]: {response.content}")],
            "next_worker": "FINISH"
        }
def supervisor_node(state:SkyTakeoutState):
    current_status = state.get("refund_status", "NONE")
    # -------------------------------------------------------------------------
    # 防御层 1：代码级终态短路（0 延迟、0 Token、100% 确定性）
    # 如果退款已经处于终态（APPROVED / REJECTED），坚决不打扰 LLM，直接闭环退出！
    # -------------------------------------------------------------------------
    if current_status in ["APPROVED", "REJECTED"]:
        logger.info(
            f"[Supervisor Guard] 🛡️ Fast-path exit: Order refund already settled as '{current_status}'. "
            f"Bypassing LLM call."
        )
        return {"next_worker": "FINISH"}
    supervisor_prompt = (
        "You are the Central Orchestration Supervisor for Sky Takeout.\n"
        "Route customer query to the most qualified specialist:\n"
         "=== LIVE SYSTEM STATUS ===\n"
            f"- Target Order ID: {state.get('order_id', 'N/A')}\n"
            f"- Current Refund Status: {current_status}\n"
            f"- Refund Amount: ${state.get('refund_amount', 0.0):.2f}\n"
            "===========================\n\n"
        "  1. 'dish_advisor': For meal suggestions, calories, taste, nutrition.\n"
        "  2. 'order_manager': For delivery tracking, ETA, courier location.\n"
        "  3. 'refund_officer': For refund requests, cold food complaints, cancel orders.\n"
        "  4. 'FINISH': If query is fully answered or greeting."
    )
    llm = get_llm()
    structured_llm = llm.with_structured_output(SupervisorDecision,method="function_calling")
    decision:SupervisorDecision = structured_llm.invoke(
        [SystemMessage(content=supervisor_prompt)]+state["messages"]
    )
    logger.info(f"[Supervisor] Routing decision -> '{decision.next_worker}' | Reason: {decision.reason}")
    return {"next_worker": decision.next_worker}

def route_from_supervisor(state:SkyTakeoutState)->Literal["dish_advisor", "order_manager", "refund_officer","__end__"]:
    target = state.get("next_worker","FINISH")
    if target == "FINISH" or not target:
        return END
    return target
def build_sky_takeout_graph():
    builder = StateGraph(SkyTakeoutState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("dish_advisor", dish_advisor_worker)
    builder.add_node("order_manager", order_manager_worker)
    builder.add_node("refund_officer", refund_officer_worker)

    builder.add_edge(START,"supervisor")
    builder.add_conditional_edges("supervisor",route_from_supervisor)

    # 专员处理完后，交还给主管进行闭环确认或退出
    builder.add_edge("dish_advisor","supervisor")
    builder.add_edge("order_manager", "supervisor")
    builder.add_edge("refund_officer", "supervisor")
    return builder.compile(checkpointer=MemorySaver())

class AsyncSessionLockManager:
    def __init__(self):
        self._locks:Dict[str,asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def acquire(self, thread_id: str) -> bool:
        async with self._guard:
            if thread_id not in self._locks:
                self._locks[thread_id] = asyncio.Lock()
        lock = self._locks[thread_id]
        if lock.locked():
            return False
        await lock.acquire()
        return True

    def release(self, thread_id: str):
        if thread_id in self._locks and self._locks[thread_id].locked():
            self._locks[thread_id].release()

class TakeoutChatRequest(BaseModel):
        session_id: str = Field(..., description="Unique user session or thread identifier")
        user_id: str = Field(default="USER_001")
        order_id: str = Field(default="ORD-001")
        query: str = Field(..., description="Customer input text")
        refund_amount: float = Field(default=0.0)
        refund_reason: str = Field(default="")


class TakeoutApproveRequest(BaseModel):
    session_id: str = Field(..., description="Target thread_id waiting at interrupt()")
    decision: Literal["APPROVED", "REJECTED"] = Field(...)
    approved_amount: float = Field(default=0.0)
    notes: str = Field(default="Manager review completed")

# fastapi gateway
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 [Gateway Lifespan] Compiling Sky Takeout Graph singleton...")
    app.state.graph = build_sky_takeout_graph()
    app.state.lock_manager = AsyncSessionLockManager()
    logger.info("✅ [Gateway Lifespan] Graph compiled and Lock Manager ready.")
    yield
    logger.info("🛑 [Gateway Lifespan] Gateway shutdown.")

api_app = FastAPI(title="test agent",lifespan=lifespan)

@api_app.post("/api/v1/takeout/chat")
async def chat_stream_endpoint(payload: TakeoutChatRequest, request: Request):
    lock_mgr: AsyncSessionLockManager = request.app.state.lock_manager
    graph = request.app.state.graph
    thread_id = payload.session_id
    # 1. 尝试获取会话锁，如果冲突直接报 429
    if not await lock_mgr.acquire(thread_id):
        raise HTTPException(status_code=429, detail=f"Session {thread_id} is currently busy. Please wait.")
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
                # 客户端断连检测
                if await request.is_disconnected():
                    logger.warning(f"Client disconnected for session {thread_id}")
                    break

                    # 推送节点完成进度
                yield {"event": "node_update", "data": json.dumps(list(event.keys()))}

            # 检查是否处于断点挂起态
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
    """
    Manager Human-in-the-Loop Resume Endpoint using Command(resume=...).
    """
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": payload.session_id}}
    snapshot = graph.get_state(config)

    if not snapshot.tasks or not snapshot.tasks[0].interrupts:
        raise HTTPException(status_code=400, detail="Target session is not waiting for approval.")

    # 唤醒图！               - Command ✅
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

# =============================================================================
# Milestone 4: End-to-End HTTP & SSE Gateway Simulation
# =============================================================================
async def run_full_api_simulation():
    """
    Spins up a live background uvicorn server on port 8099,
    and runs comprehensive E2E tests for Streaming, Concurrency Locks, and Human-in-the-Loop Resumes.
    """
    server_port = 8099
    server_config = uvicorn.Config(api_app, host="127.0.0.1", port=server_port, log_level="warning")
    server = uvicorn.Server(server_config)
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.8)  # Wait for server startup & lifespan compilation

    base_url = f"http://127.0.0.1:{server_port}"
    logger.info(f"🌐 [E2E Test] Live FastAPI server running at {base_url}")

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            # -----------------------------------------------------------------
            # Case 1: 顾客发起普通咨询，验证 SSE 流式节点推送
            # -----------------------------------------------------------------
            print("\n" + "=" * 70)
            print(" 🧪 TEST 1: SSE Streaming Customer Inquiry")
            print("=" * 70)
            chat_payload = {
                "session_id": "CLIENT_SESSION_ADVICE_01",
                "order_id": "ORD-001",
                "query": "Recommend a high-protein salmon meal under 500 kcal."
            }
            async with client.stream("POST", "/api/v1/takeout/chat", json=chat_payload) as resp:
                print(f"HTTP Status: {resp.status_code} | Content-Type: {resp.headers.get('content-type')}")
                current_event = None
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("event: "):
                        current_event = line.replace("event: ", "").strip()
                    elif line.startswith("data: "):
                        raw_data = line.replace("data: ", "").strip()
                        print(f"  [SSE Event: {current_event}] -> {raw_data}")

            # -----------------------------------------------------------------
            # Case 2: 并发防抖测试（同一 session 快速并发连击，应触发 HTTP 429）
            # -----------------------------------------------------------------
            print("\n" + "=" * 70)
            print(" 🧪 TEST 2: Concurrency Lock & Anti-Shake (Rapid Double Click)")
            print("=" * 70)
            busy_payload = {
                "session_id": "RAPID_CLICK_SESSION_02",
                "order_id": "ORD-002",
                "query": "Where is my delivery right now?"
            }

            async def send_chat_req():
                return await client.post("/api/v1/takeout/chat", json=busy_payload)

            # 连续快速并发触发两个请求
            req_a, req_b = await asyncio.gather(send_chat_req(), send_chat_req(), return_exceptions=True)
            statuses = [getattr(r, "status_code", "ERROR") for r in [req_a, req_b]]
            print(f"Concurrent Request Status Codes: {statuses}")
            if 429 in statuses:
                print("  ✅ [SUCCESS] Session Mutex Lock accurately intercepted double-click with HTTP 429!")

            # -----------------------------------------------------------------
            # Case 3: 大额退款触发 interrupt() 挂起告警 + 店长后台审批唤醒
            # -----------------------------------------------------------------
            print("\n" + "=" * 70)
            print(" 🧪 TEST 3: High-Value Refund ($120) Interrupt Alert & Manager Resume")
            print("=" * 70)
            refund_session_id = "REFUND_HTTP_SESSION_03"
            refund_payload = {
                "session_id": refund_session_id,
                "order_id": "ORD-TAKEOUT-9903",
                "query": "10 steaks arrived icy cold! I demand a $120 refund immediately!",
                "refund_amount": 120.0,
                "refund_reason": "Icy cold food"
            }

            # 步骤 3.1: 顾客发起退款，SSE 接收挂起事件
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
                            print(f"  🚨 [CRITICAL ALERT RECEIVED OVER SSE]:\n     {raw_data}")

            # 步骤 3.2: 模拟店长在后台审批面板点击“批准退款 $100”
            print("\n  👉 Manager reviews alert and approves $100 payout via /approve endpoint...")
            approve_payload = {
                "session_id": refund_session_id,
                "decision": "APPROVED",
                "approved_amount": 100.0,
                "notes": "Verified cold steak delivery with rider. Approved $100 settlement."
            }
            approve_resp = await client.post("/api/v1/takeout/approve", json=approve_payload)
            print(f"  Approval API Status: {approve_resp.status_code}")
            print(f"  Approval Response Body:\n  {json.dumps(approve_resp.json(), indent=4, ensure_ascii=False)}")

    finally:
        print("\n" + "=" * 70)
        print(" 🏁 E2E SIMULATION COMPLETE - SHUTTING DOWN GATEWAY")
        print("=" * 70)
        server.should_exit = True
        await server_task

if __name__ == "__main__":
    asyncio.run(run_full_api_simulation())