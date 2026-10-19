import sqlite3
from logging import Logger
from typing import TypedDict, Literal

from dotenv import find_dotenv, load_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from loguru import logger

from graph_utils import print_graph_mermaid

load_dotenv(find_dotenv())

# Layer 1: Schema Definition
class ContractState(TypedDict):
    contract_title:str
    amount_usd:float
    audit_status:str
    final_disposition:str

# Layer 2: Workflow Nodes & Routing
def drafter_node(state:ContractState):
    return {"audit_status":"PENDING_AUDIT"}

def risk_audit_node(state:ContractState):
    if state["amount_usd"]>50000:
        return {"audit_status":"REJECTED","final_disposition":"CONTRACT_ABORTED"}
    else:
        return{"audit_status":"APPROVED","final_deposition":"READ_FOR_SIGNATURE"}

# which used for conditional
def router_after_audit(state:ContractState)->Literal["archiver","__end__"]:
    if state["audit_status"] == "APPROVED":
        return "archiver"
    else:
        return END
def archive_node(state:ContractState):
    return {"final_deposition":"ARCHIVED_SUCCESSFULLY"}

def build_contract_graph(checkpointer:SqliteSaver):
    builder = StateGraph(ContractState)
    builder.add_node("drafter",drafter_node)
    builder.add_node("risk_audit",risk_audit_node)
    builder.add_node("archiver",archive_node)

    builder.add_edge(START,"drafter")
    builder.add_edge("drafter","risk_audit")

    builder.add_conditional_edges(
        "risk_audit",
        router_after_audit
    )
    builder.add_edge("archiver",END)
    return builder.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    db_connection = sqlite3.connect(":memory:",check_same_thread=False)
    checkpointer = SqliteSaver(db_connection)

    app = build_contract_graph(checkpointer)

    session_config = {"configurable": {"thread_id": "CONTRACT_WORKFLOW_2026"}}

    # Phase 1: Initial Run (With Mistaken Huge Amount -> Triggers Rejection)
    initial_payload = {
        "contract_title": "Enterprise Cloud Migration",
        "amount_usd": 1000000.0,  # Human mistake! Exceeds limit
        "audit_status": "UNINITIALIZED",
        "final_disposition": "IN_PROGRESS"
    }
    app.invoke(initial_payload,config=session_config)

    # Phase 2: Inspecting History Tree (git log)  [(Time Travel Log)] ✅✅✅
    history = list(app.get_state_history(session_config))
    for idx,snap in enumerate(history):
        c_id = snap.config['configurable']['checkpoint_id']
        next_step = snap.next
        amt = snap.values.get("amount_usd","N/A")
        status = snap.values.get("audit_status","N/A")
        logger.info(f"  [{idx}] Checkpoint ID: {c_id[:18]}... | Amount: ${amt} | Audit: {status:<15} | Next Node:{next_step}")

    # Phase 3: Time Travel! Find the checkpoint right after 'drafter'
    target_snapshot = None
    for snap in history:
        if snap.next ==("risk_audit",):
            target_snapshot = snap
            break
    logger.info(f"\n❌Targeting Checkpoint for Rollback: {target_snapshot.config['configurable']['checkpoint_id']}")
    logger.info(f"❌Original State Values at this point: {target_snapshot.values}")

    # Phase 4: State Editing (Forking a New Branch)
    # Create a config pointing specifically to that historical checkpoint
    rollback_config = target_snapshot.config
    # ✅Update the state at that exact point in time!
    forked_config = app.update_state(
        rollback_config,
        values={"amount_usd":10000.0},# Corrected amount!
        as_node="drafter"# Act as if 'drafter' produced this corrected value
    )
    logger.info(f"✅✅Forked Checkpoint ID created: {forked_config['configurable']['checkpoint_id']}")

    # Phase 5: Resume Execution along the Forked Timeline!
    # Pass None as payload because the state already exists in the checkpoint!
    final_result = app.invoke(None,config=forked_config)

    print("\n===✅✅ Final State on New Branch✅✅ ===")
    print(f"Final Disposition: {final_result['final_disposition']}")
    print(f"Final Amount: ${final_result['amount_usd']:,.2f}")
    print(f"Final Audit Status: {final_result['audit_status']}")
    print_graph_mermaid(app,"03")
