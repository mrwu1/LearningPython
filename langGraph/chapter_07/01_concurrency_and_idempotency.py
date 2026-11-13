"""
================================================================================
【LangGraph 阶段七：生产高可用与分布式防御】第 1 课：会话互斥并发锁与财务级工具幂等性（Concurrency & Idempotency）
================================================================================
【核心学习目标】：
1. 掌握会话级互斥并发锁（Session Mutex Lock）：
   - 核心痛点：用户狂点按钮或网络抖动发送并发请求时，同一个 `thread_id` 若并发执行，会导致检查点状态覆盖冲突与竞态破坏。
   - 解决方案：基于 `thread_id` 施加非阻塞互斥锁；同一会话同一时刻只允许一个请求执行，并发重复请求直接返回 429 Too Many Requests 快速拒绝。
2. 掌握关键业务工具的幂等性防御（Tool Idempotency）：
   - 核心痛点：大模型在受控循环中由于超时重试或思维漂移，可能会重复调用扣款工具，导致资金重复扣减（Double-Spending）。
   - 解决方案：引入幂等账本（Idempotency Ledger），以 `order_id` 为唯一业务幂等键；命中已处理记录时直接返回缓存凭证，坚决不重复扣款！
================================================================================
"""

import sys
import asyncio
from pathlib import Path
from typing import TypedDict, Annotated, Dict
from dotenv import find_dotenv, load_dotenv
from loguru import logger

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(find_dotenv())

from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph, add_messages
from langchain_core.messages import BaseMessage
from langchain_core.tools import tool


# ==============================================================================
# 第一层：会话级互斥并发锁管理器（Session-Level Mutex Lock）
# ==============================================================================
class AsyncSessionLockManager:
    """
    【会话互斥并发控制器】：
    以 thread_id 为粒度进行加锁。
    保证同一会话的并发请求被严格拦截或串行化，而不同用户的会话完全并发不受影响。
    （注：在多 Pod 的 Kubernetes 分布式生产环境中，本内存锁可无缝平替为 Redis 分布式锁：
     redis.set(f"lock:session:{thread_id}", token, nx=True, ex=30)）
    """
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_guard = asyncio.Lock()

    async def acquire_session_lock(self, thread_id: str) -> bool:
        """非阻塞尝试获取会话锁：如果当前会话已有任务正在运行，立刻返回 False。"""
        async with self._global_guard:
            if thread_id not in self._locks:
                self._locks[thread_id] = asyncio.Lock()
        
        lock = self._locks[thread_id]
        if lock.locked():
            return False  # 已被占用，拒绝并发
        
        await lock.acquire()
        return True

    def release_session_lock(self, thread_id: str):
        """释放指定会话的互斥锁。"""
        if thread_id in self._locks and self._locks[thread_id].locked():
            self._locks[thread_id].release()


# ==============================================================================
# 第二层：幂等账本与受保护的资金扣减工具
# ==============================================================================
# 模拟底层用户钱包数据库
user_wallet = {"balance": 100.00}

# 幂等交易账本（保存已处理的交易收据）：{order_id: receipt}
idempotency_ledger = {}


@tool
def execute_order_payout(order_id: str, amount: float) -> str:
    """
    执行订单资金扣减支付。受幂等键严格保护！
    防止大模型因自动重试或幻觉多次调用而导致重复扣款。
    """
    # 1. 【防线一：核查幂等账本】（Cache Hit 命中）
    if order_id in idempotency_ledger:
        cached_receipt = idempotency_ledger[order_id]
        logger.warning(f"  [幂等防护罩 🛡️] 侦测到重复调用！订单 {order_id} 此前已完成扣款。")
        logger.warning(f"  [幂等防护罩 🛡️] 直接返回历史交易凭据，拦截重复扣除余额！")
        return f"[IDEMPOTENT_CACHE_HIT] 交易 {cached_receipt['tx_id']} 此前已确认，已扣除: ${cached_receipt['amount']}"

    # 2. 【防线二：余额充盈性校验】
    if user_wallet["balance"] < amount:
        return f"[FAILED] 钱包余额不足，当前余额: ${user_wallet['balance']:,.2f}"

    # 3. 【真实扣减资金】
    user_wallet["balance"] -= amount
    tx_id = f"TX-PAY-{len(idempotency_ledger) + 1:04d}"
    
    # 4. 【写入幂等流水账本】
    receipt = {
        "tx_id": tx_id,
        "order_id": order_id,
        "amount": amount,
        "remaining_balance": user_wallet["balance"]
    }
    idempotency_ledger[order_id] = receipt

    logger.info(f"  [财务出款 💰] 成功扣除 ${amount:,.2f}。扣后最新余额: ${user_wallet['balance']:,.2f}")
    return f"[SUCCESS] 交易流水号 {tx_id} 结算完毕，成功扣款: ${amount:,.2f}"


# ==============================================================================
# 第三层：图定义
# ==============================================================================
class AgentState(TypedDict):
    order_id: str
    messages: Annotated[list[BaseMessage], add_messages]
    result: str


async def payout_agent_node(state: AgentState):
    """模拟智能体执行支付工具节点。"""
    order_id = state["order_id"]
    # 故意模拟 0.5 秒的网络与计算延迟，用于测试高并发竞态
    await asyncio.sleep(0.5)
    
    # 调用受到幂等保护的工具函数
    tool_output = execute_order_payout.invoke({"order_id": order_id, "amount": 45.00})
    return {"result": tool_output}


def build_payout_graph():
    builder = StateGraph(AgentState)
    builder.add_node("payout_worker", payout_agent_node)
    builder.add_edge(START, "payout_worker")
    builder.add_edge("payout_worker", END)
    return builder.compile(checkpointer=MemorySaver())


# ==============================================================================
# 第四层：生产级实战演练与防御验证
# ==============================================================================
async def main():
    app = build_payout_graph()
    lock_manager = AsyncSessionLockManager()

    # --------------------------------------------------------------------------
    # 演练 1：会话级互斥并发锁（防御用户超高频双击与重放刷单）
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("🛡️ 【演练 1】：会话级并发互斥锁（拦截高频重复点击）")
    print("=" * 65)

    shared_thread_id = "USER_SESSION_ALEX_99"

    async def simulate_incoming_request(request_id: str, delay: float):
        await asyncio.sleep(delay)
        logger.info(f"[{request_id}] 到达网关，请求会话: '{shared_thread_id}'")

        # 1. 尝试获取会话锁
        acquired = await lock_manager.acquire_session_lock(shared_thread_id)
        if not acquired:
            logger.error(f"[{request_id}] ❌ 429 CONFLICT: 会话 '{shared_thread_id}' 正在处理中，拒绝并发！")
            return {"status": "REJECTED_429_TOO_MANY_REQUESTS"}

        try:
            logger.info(f"[{request_id}] 🔒 成功获取锁，开始执行图任务...")
            config = {"configurable": {"thread_id": shared_thread_id}}
            result = await app.ainvoke(
                {"order_id": "ORD-INIT-01", "messages": [], "result": ""},
                config=config
            )
            logger.info(f"[{request_id}] ✅ 图任务执行完成。")
            return {"status": "SUCCESS", "data": result}
        finally:
            lock_manager.release_session_lock(shared_thread_id)
            logger.info(f"[{request_id}] 🔓 释放锁完成。")

    # 模拟客户端在几乎同一时刻（相差 50ms）发起了两次完全并发的点击
    logger.info("模拟请求 A (0ms) 与请求 B (50ms) 同时争抢同一个会话...")
    results = await asyncio.gather(
        simulate_incoming_request("REQUEST_A", delay=0.0),
        simulate_incoming_request("REQUEST_B", delay=0.05)
    )

    print("\n并发执行裁判裁决:")
    print(f"  • 请求 A 状态: {results[0]['status']}")
    print(f"  • 请求 B 状态: {results[1]['status']} (成功被拦截，避免了会话级竞态冲突！)")

    # --------------------------------------------------------------------------
    # 演练 2：工具幂等性防御（彻底杜绝资金重复扣减）
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("🛡️ 【演练 2】：财务工具幂等性防护（防止模型重试导致重复扣款）")
    print("=" * 65)

    # 重置初始测试余额
    user_wallet["balance"] = 100.00
    test_order = "ORD-TAKEOUT-8888"
    print(f"用户初始钱包余额: ${user_wallet['balance']:,.2f}\n")

    # 调用 1：首次合法正常扣款 $45.00
    logger.info("--- [调用 1] 第一次尝试扣款 $45.00 ---")
    resp_1 = execute_order_payout.invoke({"order_id": test_order, "amount": 45.00})
    print(f"调用 1 结果: {resp_1}")
    print(f"调用 1 后的钱包余额: ${user_wallet['balance']:,.2f}\n")

    # 调用 2：由于网络超时重试或 LLM 误重复发起相同的 order_id 扣款！
    logger.info("--- [调用 2] 重复发起相同的扣款请求 (相同 order_id) ---")
    resp_2 = execute_order_payout.invoke({"order_id": test_order, "amount": 45.00})
    print(f"调用 2 结果: {resp_2}")
    print(f"调用 2 后的钱包余额: ${user_wallet['balance']:,.2f}")

    print("\n" + "=" * 65)
    if user_wallet["balance"] == 55.00:
        print("🎯 最终安全审查结论: 完美拦截！余额维持 $55.00，资金零泄露！")
    else:
        print("❌ 严重事故: 发生资金重复扣减！")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
