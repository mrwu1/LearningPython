import sys
import asyncio
from pathlib import Path
from typing import TypedDict, Annotated, Dict
from dotenv import find_dotenv, load_dotenv
from loguru import logger

from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph, add_messages
from langchain_core.messages import BaseMessage
from langchain_core.tools import tool

# Standard environment & sys.path setup
load_dotenv(find_dotenv())
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ==============================================================================
# Layer 1: Concurrency Control - Session-Level Mutex Lock
# ==============================================================================
class AsyncSessionLockManager:
    """
    Manages session-level locks keyed by thread_id.
    Ensures that concurrent requests to the SAME session are serialized or rejected,
    while DIFFERENT sessions execute concurrently without blocking.
    (In a multi-pod Kubernetes production environment, this is replaced by Redis Distributed Locks:
     redis.set(f"lock:session:{thread_id}", token, nx=True, ex=30))
    """
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_guard = asyncio.Lock()

    async def acquire_session_lock(self, thread_id: str) -> bool:
        """Attempts to acquire lock without blocking. Returns False if already locked."""
        async with self._global_guard:
            if thread_id not in self._locks:
                self._locks[thread_id] = asyncio.Lock()
        
        # Check if already locked (Non-blocking acquisition)
        lock = self._locks[thread_id]
        if lock.locked():
            return False
        
        await lock.acquire()
        return True

    def release_session_lock(self, thread_id: str):
        """Releases the lock for this thread."""
        if thread_id in self._locks and self._locks[thread_id].locked():
            self._locks[thread_id].release()

# ==============================================================================
# Layer 2: Idempotent Ledger & Protected Financial Tool
# ==============================================================================
# Simulated database records
user_wallet = {"balance": 100.00}
idempotency_ledger = {} # Stores processed transaction receipts: {idempotency_key: receipt}

@tool
def execute_order_payout(order_id: str, amount: float) -> str:
    """
    Disburses funds from user wallet. Protected by Idempotency Key!
    Prevents double-spending when retried or called multiple times by LLM.
    """
    # 1. Check Idempotency Ledger (Cache Hit Check)
    if order_id in idempotency_ledger:
        cached_receipt = idempotency_ledger[order_id]
        logger.warning(f"  [Idempotency Shield] 🛡️ REPLAY DETECTED! Order {order_id} already processed.")
        logger.warning(f"  [Idempotency Shield] Returning cached receipt without deducting balance.")
        return f"[IDEMPOTENT_CACHE_HIT] Transaction {cached_receipt['tx_id']} already confirmed. Deducted: ${cached_receipt['amount']}"

    # 2. Check Wallet Balance
    if user_wallet["balance"] < amount:
        return f"[FAILED] Insufficient wallet balance: ${user_wallet['balance']:,.2f}"

    # 3. Execute Real Financial Deduction
    user_wallet["balance"] -= amount
    tx_id = f"TX-PAY-{len(idempotency_ledger) + 1:04d}"
    
    # 4. Record to Idempotency Ledger
    receipt = {
        "tx_id": tx_id,
        "order_id": order_id,
        "amount": amount,
        "remaining_balance": user_wallet["balance"]
    }
    idempotency_ledger[order_id] = receipt

    logger.info(f"  [Financial Payout] 💰 SUCCESS: Deducted ${amount:,.2f}. New Balance: ${user_wallet['balance']:,.2f}")
    return f"[SUCCESS] Transaction {tx_id} completed. Disbursed: ${amount:,.2f}"

# ==============================================================================
# Layer 3: Graph Definition
# ==============================================================================
class AgentState(TypedDict):
    order_id: str
    messages: Annotated[list[BaseMessage], add_messages]
    result: str

async def payout_agent_node(state: AgentState):
    """Simulates agent executing the payment tool."""
    order_id = state["order_id"]
    # Simulating deliberate processing delay to test concurrency race condition
    await asyncio.sleep(0.5)
    
    # Invoke the idempotent tool
    tool_output = execute_order_payout.invoke({"order_id": order_id, "amount": 45.00})
    return {"result": tool_output}

def build_payout_graph():
    builder = StateGraph(AgentState)
    builder.add_node("payout_worker", payout_agent_node)
    builder.add_edge(START, "payout_worker")
    builder.add_edge("payout_worker", END)
    return builder.compile(checkpointer=MemorySaver())

# ==============================================================================
# Layer 4: Enterprise Production Verification Sandboxes
# ==============================================================================
async def main():
    app = build_payout_graph()
    lock_manager = AsyncSessionLockManager()

    # --------------------------------------------------------------------------
    # Test 1: Concurrency Mutex Lock (Defending against rapid double-clicks)
    # --------------------------------------------------------------------------
    print("=" * 65)
    print(" 🛡️ TEST 1: SESSION-LEVEL CONCURRENCY MUTEX LOCK")
    print("=" * 65)

    shared_thread_id = "USER_SESSION_ALEX_99"

    async def simulate_incoming_request(request_id: str, delay: float):
        await asyncio.sleep(delay)
        logger.info(f"[{request_id}] Arrived at gateway for session '{shared_thread_id}'")

        # 1. Attempt to acquire session lock
        acquired = await lock_manager.acquire_session_lock(shared_thread_id)
        if not acquired:
            logger.error(f"[{request_id}] ❌ 429 CONFLICT: Session '{shared_thread_id}' is busy. Request dropped!")
            return {"status": "REJECTED_429_TOO_MANY_REQUESTS"}

        try:
            logger.info(f"[{request_id}] 🔒 Lock acquired! Executing graph...")
            config = {"configurable": {"thread_id": shared_thread_id}}
            result = await app.ainvoke(
                {"order_id": "ORD-INIT-01", "messages": [], "result": ""},
                config=config
            )
            logger.info(f"[{request_id}] ✅ Graph execution finished.")
            return {"status": "SUCCESS", "data": result}
        finally:
            lock_manager.release_session_lock(shared_thread_id)
            logger.info(f"[{request_id}] 🔓 Lock released.")

    # Fire two concurrent requests almost simultaneously (0ms vs 50ms)
    logger.info("Firing Request A and Request B concurrently targeting the SAME session...")
    results = await asyncio.gather(
        simulate_incoming_request("REQUEST_A", delay=0.0),
        simulate_incoming_request("REQUEST_B", delay=0.05)
    )

    print("\nConcurrent Execution Verdict:")
    print(f"  • Request A Status: {results[0]['status']}")
    print(f"  • Request B Status: {results[1]['status']} (Successfully intercepted to prevent race condition!)")

    # --------------------------------------------------------------------------
    # Test 2: Tool Idempotency (Defending against double-spending / retries)
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print(" 🛡️ TEST 2: TOOL IDEMPOTENCY DEFENSE (DOUBLE-SPEND PROTECTION)")
    print("=" * 65)

    # Reset wallet balance for clean test
    user_wallet["balance"] = 100.00
    test_order = "ORD-TAKEOUT-8888"
    print(f"Initial User Wallet Balance: ${user_wallet['balance']:,.2f}\n")

    # Call 1: Normal First Payout
    logger.info("--- Call 1: First Attempt to Pay $45.00 ---")
    resp_1 = execute_order_payout.invoke({"order_id": test_order, "amount": 45.00})
    print(f"Call 1 Result: {resp_1}")
    print(f"Wallet Balance after Call 1: ${user_wallet['balance']:,.2f}\n")

    # Call 2: Accidental / Malicious / Retry Duplicate Payout with SAME order_id!
    logger.info("--- Call 2: Duplicate Attempt to Pay $45.00 (Same order_id) ---")
    resp_2 = execute_order_payout.invoke({"order_id": test_order, "amount": 45.00})
    print(f"Call 2 Result: {resp_2}")
    print(f"Wallet Balance after Call 2: ${user_wallet['balance']:,.2f}")

    print("\n" + "=" * 65)
    if user_wallet["balance"] == 55.00:
        print(" 🎯 FINAL VERDICT: ZERO FINANCIAL LEAKAGE! Balance remained $55.00.")
    else:
        print(" ❌ FATAL ERROR: Double spending occurred!")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())