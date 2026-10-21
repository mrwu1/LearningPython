import sys
from pathlib import Path
from typing import TypedDict, Literal
from dotenv import find_dotenv, load_dotenv
from loguru import logger

from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph

# Standard environment & sys.path setup
load_dotenv(find_dotenv())
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ==============================================================================
# Layer 1: Simulated External Microservice Databases
# ==============================================================================
# Warehouse microservice
warehouse_db = {"Wellington_Steak": 10}

# Financial wallet microservice
wallet_db = {"balance": 100.00}

# ==============================================================================
# Layer 2: Schema Definition with Saga Compensation Stack
# ==============================================================================
class SagaOrderState(TypedDict):
    order_id: str
    dish_name: str
    amount: float
    # Saga LIFO Stack:‼️ Records reversible steps in order
    compensation_stack: list[str]
    # Flow tracking
    current_error: str
    order_disposition: str

# ==============================================================================
# Layer 3: Forward Nodes (Positive Transaction Actions)
# ==============================================================================
def reserve_inventory_node(state: SagaOrderState):
    """Forward Step 1: Reserves dish inventory in warehouse."""
    dish = state["dish_name"]
    logger.info(f"[Forward T1: Inventory] Reserving 1x {dish} in warehouse...")

    if warehouse_db[dish] <= 0:
        return {"current_error": "OUT_OF_STOCK"}

    # Execute reservation
    warehouse_db[dish] -= 1
    logger.info(f"  -> Stock reserved! Remaining: {warehouse_db[dish]}")

    # Push compensating action onto stack!
    new_stack = state.get("compensation_stack", []).copy()
    new_stack.append("ROLLBACK_INVENTORY")
    return {"compensation_stack": new_stack}

def deduct_payment_node(state: SagaOrderState):
    """Forward Step 2: Deducts funds from user wallet."""
    amount = state["amount"]
    logger.info(f"[Forward T2: Payment] Deducting ${amount:,.2f} from user wallet...")

    if wallet_db["balance"] < amount:
        return {"current_error": "INSUFFICIENT_FUNDS"}

    # ‼️Execute financial deduction
    wallet_db["balance"] -= amount
    logger.info(f"  -> Funds deducted! Remaining balance: ${wallet_db['balance']:,.2f}")

    # Push compensating action onto stack!
    new_stack = state["compensation_stack"].copy()
    new_stack.append("REFUND_PAYMENT")
    return {"compensation_stack": new_stack}

def dispatch_courier_node(state: SagaOrderState):
    """
    Forward Step 3: Calls external third-party logistics API.
    Simulates external outage (e.g. 503 No Couriers in severe storm).
    """
    logger.info("[Forward T3: Courier] Contacting Third-Party Courier API (SF/Meituan)...")
    logger.error("  ❌ [API FAILURE 503] Extreme rainstorm! No couriers available in 5km radius.")

    # Simulating external failure
    return {"current_error": "COURIER_DISPATCH_TIMEOUT_503"}

# ==============================================================================
# Layer 4:‼️ Backward Compensation Nodes (Saga Reverse Rollback)
# ==============================================================================
def saga_compensator_node(state: SagaOrderState):
    """
        Saga Compensating Controller:
        Executes compensating actions in reverse order (LIFO) until stack is exhausted!
    """
    stack = state.get("compensation_stack", []).copy()
    dish = state["dish_name"]
    amount = state["amount"]

    logger.warning("\n" + "=" * 60)
    logger.warning(f" ⚠️ SAGA COMPENSATION ACTIVATED DUE TO: {state['current_error']}")
    logger.warning(f" Total reversible actions in stack: {len(stack)}")
    logger.warning("=" * 60)

    # Pop and compensate in reverse order!
    while stack:
        action = stack.pop()
        if action == "REFUND_PAYMENT":
            wallet_db["balance"] += amount # ‼️
            logger.info(f"  [Compensating C2] 💸 Refunded ${amount:,.2f} to wallet. Balance restored: ${wallet_db['balance']:,.2f}")
        elif action == "ROLLBACK_INVENTORY":
            warehouse_db[dish] += 1 #‼️
            logger.info(f"  [Compensating C1] 📦 Released 1x {dish} to warehouse. Stock restored: {warehouse_db[dish]}")

    logger.warning("✅ SAGA COMPENSATION COMPLETED. Zero state discrepancy left in DB.")
    return {
        "compensation_stack": [],
        "order_disposition": "CANCELLED_FULLY_COMPENSATED"
    }

# ==============================================================================
# Layer 5: Routers and Graph Assembly
# ==============================================================================
def route_after_inventory(state: SagaOrderState) -> Literal["deduct_payment", "saga_compensator"]:
    if state.get("current_error"):
        return "saga_compensator"
    return "deduct_payment"

def route_after_payment(state: SagaOrderState) -> Literal["dispatch_courier", "saga_compensator"]:
    if state.get("current_error"):
        return "saga_compensator"
    return "dispatch_courier"
# ‼️
def route_after_courier(state: SagaOrderState) -> Literal["confirm_order", "saga_compensator"]:
    if state.get("current_error"):
        return "saga_compensator"
    return "confirm_order"

def confirm_order_node(state: SagaOrderState):
    logger.info("🎉 Order completely successful!")
    return {"order_disposition": "FULFILLED"}

def build_saga_graph():
    builder = StateGraph(SagaOrderState)

    # Forward nodes
    builder.add_node("reserve_inventory", reserve_inventory_node)
    builder.add_node("deduct_payment", deduct_payment_node)
    builder.add_node("dispatch_courier", dispatch_courier_node)
    builder.add_node("confirm_order", confirm_order_node)

    # Backward compensating node ‼️
    builder.add_node("saga_compensator", saga_compensator_node)

    # Forward routing
    builder.add_edge(START, "reserve_inventory")
    builder.add_conditional_edges("reserve_inventory", route_after_inventory)
    builder.add_conditional_edges("deduct_payment", route_after_payment)
    builder.add_conditional_edges("dispatch_courier", route_after_courier)

    # Final terminations
    builder.add_edge("confirm_order", END)
    builder.add_edge("saga_compensator", END)

    return builder.compile(checkpointer=MemorySaver())

# ==============================================================================
# Layer 6: Execution & Zero-Discrepancy Verification Sandbox
# ==============================================================================
if __name__ == "__main__":
    app = build_saga_graph()

    print("=" * 65)
    print(" 🛒 INITIAL STATE BEFORE ORDER PLACEMENT")
    print(f"  • Warehouse Steak Stock: {warehouse_db['Wellington_Steak']}")
    print(f"  • User Wallet Balance:   ${wallet_db['balance']:,.2f}")
    print("=" * 65 + "\n")

    order_payload = {
        "order_id": "ORD-SAGA-991",
        "dish_name": "Wellington_Steak",
        "amount": 68.00,
        "compensation_stack": [],
        "current_error": "",
        "order_disposition": "IN_PROGRESS"
    }

    config = {"configurable": {"thread_id": "SESSION_SAGA_TEST"}}
    final_state = app.invoke(order_payload, config=config)

    print("\n" + "=" * 65)
    print(" 🏁 FINAL AUDIT VERDICT AFTER WORKFLOW COMPLETION")
    print("=" * 65)
    print(f"Order Disposition:       {final_state['order_disposition']}")
    print(f"Failure Reason Recorded: {final_state['current_error']}")
    print(f"Post-Recovery Warehouse Stock: {warehouse_db['Wellington_Steak']} (Expected: 10)")
    print(f"Post-Recovery Wallet Balance:   ${wallet_db['balance']:,.2f} (Expected: $100.00)")

    if warehouse_db['Wellington_Steak'] == 10 and wallet_db['balance'] == 100.00:
        print("\n🎯 SAGA PATTERN PASSED 100%! All partial updates successfully rolled back!")
    else:
        print("\n❌ CRITICAL DEFECT: Transaction leaked dirty state!")