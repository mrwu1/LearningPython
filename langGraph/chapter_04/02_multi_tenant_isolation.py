import operator
import sqlite3
from typing import TypedDict, Annotated

from dotenv import load_dotenv, find_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph

load_dotenv(find_dotenv())


class SubgraphState(TypedDict):
    """Internal state exclusive to the child audit subgraph."""
    audit_notes:Annotated[list[str], operator.add]

class ParentState(TypedDict):
    customer_notes:Annotated[list[str],operator.add]

def risk_audit_node(state:SubgraphState):
    return {"audit_notes":["Risk check PASSED: No sanctions detected."]}

def build_risk_subgraph():
    sub_builder = StateGraph(SubgraphState)
    sub_builder.add_node("audit_worker",risk_audit_node)

    sub_builder.add_edge(START,"audit_worker")
    sub_builder.add_edge("audit_worker", END)
    return sub_builder.compile()


#-------------------PARENT-------------------------------

def customer_service_node(state:ParentState):
    """Handles direct customer communication."""
    return {"customer_notes":["customer request registered successfully."]}
def build_parent_graph(checkpointer:SqliteSaver):
    # fetch the sub graph
    risk_subgraph = build_risk_subgraph()
    parent_builder = StateGraph(ParentState)
    parent_builder.add_node("customer_service",customer_service_node)
    parent_builder.add_node("internal_risk_subgraph",risk_subgraph)

    parent_builder.add_edge(START,"customer_service")
    parent_builder.add_edge("customer_service","internal_risk_subgraph")
    parent_builder.add_edge("internal_risk_subgraph", END)

    return parent_builder.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    db_connection = sqlite3.connect("checkpoints_sub.db", check_same_thread=False)
    checkpointer = SqliteSaver(db_connection)
    app = build_parent_graph(checkpointer) #bind the checkpointer config

    # 1. Enterprise Multi-Tenant Thread ID Generation
    # Standard format: {tenant_id}:{user_id}:{session_id}
    tenant_apple_thread = "TENANT_APPLE:USER_ALICE:SESSION_1001"
    tenant_tesla_thread = "TENANT_TESLA:USER_BOB:SESSION_2002"

    config_apple = {"configurable": {"thread_id": tenant_apple_thread}}
    config_tesla = {"configurable": {"thread_id": tenant_tesla_thread}}

    print("=== Step 1: Executing Tenant Apple Workflow ===")
    app.invoke({"customer_notes": ["Apple Order: 50,000 M4 chips."]}, config=config_apple)

    print("\n=== Step 2: Executing Tenant Tesla Workflow ===")
    app.invoke({"customer_notes": ["Tesla Order: 1,000 Optimus robots."]}, config=config_tesla)

    # 2. Verify Multi-Tenant Isolation
    apple_state = app.get_state(config_apple)
    tesla_state = app.get_state(config_tesla)

    print("\n=== Step 3: Verifying Tenant Data Isolation ===")
    print(f"Apple Session Notes: {apple_state.values['customer_notes']}")
    print(f"Tesla Session Notes: {tesla_state.values['customer_notes']}")

    # 3. Deep-Dive: Inspecting Subgraph checkpoint_ns (Namespaces)
    print("\n=== Step 4: Inspecting Hierarchical Namespaces (checkpoint_ns) ===")

    # Query all snapshots for Apple's thread including subgraphs
    subgraph_snapshots = list(app.get_state_history(config_apple))

    print(f"Total snapshots recorded for thread [{tenant_apple_thread}]: {len(subgraph_snapshots)}")
    for idx, snapshot in enumerate(subgraph_snapshots):
        ns = snapshot.config["configurable"].get("checkpoint_ns", "root")
        node_checkpoint_id = snapshot.config["configurable"]["checkpoint_id"]
        print(f"  [{idx}] Namespace: {repr(ns):<35} | Checkpoint ID: {node_checkpoint_id}")








