from typing import TypedDict, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import interrupt, Command
from loguru import logger


# Layer 1: Schema Definition

class RefundState(TypedDict):
    order_id:str
    refund_amount:float
    reason:str
    approval_status:str # PENDING_REVIEW | APPROVED | AUTO_APPROVED
    reviewer_notes:str
    payout_status:str

 # Layer 2: Business Logic Nodes with Dynamic Interrupt
def intake_request_node(state: RefundState):
        """Validates the inbound refund ticket."""
        print(f"\n[Intake Node] Processing ticket: {state['order_id']} | Requested: ${state['refund_amount']:,.2f}")
        return {"payout_status": "PENDING_REVIEW"}

def risk_evaluation_node(state:RefundState):
    amount = state["refund_amount"]
    if amount <=50:
        return {"approval_status":"AUTO_APPROVED","reviewer_notes":"System fast-track"}

    logger.info(f"the amount exceed the limit:{amount}")

    human_decision = interrupt({
        "alert":"HIGH_VALUE_REFUND_REQUIRES_APPROVAL",
        "order_id":state["order_id"],
        "requested_amount":amount,
        "reason":state["reason"]
    })
    logger.info(f"\n[Risk Node] 🚀 Graph AWOKEN by human! Decision received: {human_decision}")
    return {
        "approval_status":human_decision.get("decision","REJECTED"),
        "reviewer_notes":human_decision.get("notes","No Notes"),
        "refund_amount":human_decision.get("approved_amount",amount)
    }
def route_after_review(state:RefundState)->Literal["execute_payout","__end__"]:
    if state["approval_status"] in ["AUTO_APPROVED", "APPROVED"]:
        return "execute_payout"
    logger.info(f"[Router] 🛑 Refund was {state['approval_status']}. Skipping payout.")
    return END

def execute_payout_node(state: RefundState):
    logger.info(f"[Payout Node] 💰 SUCCESS: Disbursing ${state['refund_amount']:,.2f} for {state['order_id']} to user account.")
    return {"payout_status": "PAID_OUT"}

# Layer 3: Graph Assembly
def build_refund_graph(checkpointer:MemorySaver):
    builder = StateGraph(RefundState)
    builder.add_node("intake",intake_request_node)
    builder.add_node("risk_evalution",risk_evaluation_node)
    builder.add_node("execute_payout",execute_payout_node)

    builder.add_edge(START,"intake")
    builder.add_edge("intake","risk_evalution")
    builder.add_conditional_edges("risk_evalution",route_after_review)
    builder.add_edge("execute_payout",END)

    return builder.compile(checkpointer=checkpointer)

 # Layer 4: Enterprise Simulation (Intake -> Halt -> Webhook/Admin -> Resume)
if __name__ == "__main__":
    checkpointer = MemorySaver()
    app = build_refund_graph(checkpointer)
    # Step 1: Ingest a high-value refund request ($320.00)
    initial_ticket = {
        "order_id": "ORD-2026-9901",
        "refund_amount": 320.00,
        "reason": "Ordered 10 gourmet steaks; delivery was 3 hours late and cold.",
        "approval_status": "PENDING",
        "reviewer_notes": "",
        "payout_status": "INITIATED"
    }
    ticket_config = {"configurable": {"thread_id": "TICKET_SKY_888"}}
    app.invoke(initial_ticket,config=ticket_config)

    snapshot = app.get_state(ticket_config)
    logger.info(f"Graph Status: Next waiting node to resume: {snapshot.next}")

    # Extract the payload that was emitted by interrupt()
    interrupt_info = snapshot.tasks[0].interrupts[0].value
    logger.info("Pending Interrupt Payload extracted from database:")
    logger.info(f"  • Alert Type: {interrupt_info['alert']}")
    logger.info(f"  • Order ID: {interrupt_info['order_id']}")
    logger.info(f"  • Requested Amount: ${interrupt_info['requested_amount']:,.2f}")
    logger.info(f"  • Reason: {interrupt_info['reason']}")

    # print_graph_mermaid(app,"01")

    # 2. Add this at the bottom to simulate the manager's approval and wake up the graph:
    manager_approval_payload = {
        "decision": "APPROVED",
        "approved_amount": 280.00,
        "notes": "Verified cold delivery. Deducted $40 coupon."
    }
    logger.info("=== Resuming Graph with Command(resume=...) ===")
    #continue the loop ✅✅✅ command
    final_state = app.invoke(
        Command(resume=manager_approval_payload),
        config=ticket_config
    )
    logger.info(f"Final Approval Status: {final_state['approval_status']}")
    logger.info(f"Final Disbursed Amount: ${final_state['refund_amount']:,.2f}")
    logger.info(f"Payout Status: {final_state['payout_status']}")