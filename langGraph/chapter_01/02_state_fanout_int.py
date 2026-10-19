from typing import TypedDict

from langgraph.constants import START, END
from langgraph.graph import StateGraph

from graph_utils import print_graph_mermaid


class OrderProcessingState(TypedDict):
    order_id: str
    items: list[str]
    # Independent fields updated by concurrent worker nodes
    inventory_available: bool
    assigned_rider_id: str
    discount_amount: float
    # Final aggregation result
    final_verdict: str

def dispatch_node(state: OrderProcessingState) -> dict:
    return {"final_verdict": "PROCESSING"}

def inventory_check_node(state: OrderProcessingState) -> dict:
     return {"inventory_available": True}

def rider_dispatch_node(state: OrderProcessingState) -> dict:
    matched_rider = "RIDER-9527"
    return {"assigned_rider_id": matched_rider}

def coupon_eval_node(state: OrderProcessingState) -> dict:
    discount = 15.50
    return {"discount_amount": discount}

def order_summary_node(state: OrderProcessingState) -> dict:
    is_ready = state["inventory_available"] and bool(state["assigned_rider_id"])
    verdict = (
        f"CONFIRMED (Courier: {state['assigned_rider_id']}, Saved: ${state['discount_amount']:.2f})"
        if is_ready else "REJECTED"
    )
    return {"final_verdict": verdict}

def build_pregel_demo_graph():
    builder = StateGraph(OrderProcessingState)

    builder.add_node("dispatch",dispatch_node)

    builder.add_node("inventory",inventory_check_node)
    builder.add_node("rider",rider_dispatch_node)
    builder.add_node("coupon",coupon_eval_node)

    builder.add_node("summary",order_summary_node)

    # edge
    builder.add_edge(START,"dispatch")

    builder.add_edge("dispatch","inventory")
    builder.add_edge("dispatch","rider")
    builder.add_edge("dispatch","coupon")

    builder.add_edge("inventory","summary")
    builder.add_edge("rider","summary")
    builder.add_edge("coupon","summary")

    builder.add_edge("summary",END)

    return builder.compile()

#test
if __name__=="__main__":
    app_graph = build_pregel_demo_graph()

    # create a graph
    print_graph_mermaid(app_graph,"02")

    initial_state: OrderProcessingState = {
        "order_id": "ORD-20261017-888",
        "items": ["Cheese Pizza", "Cold Cola"],
        "inventory_available": False,
        "assigned_rider_id": "",
        "discount_amount": 0.0,
        "final_verdict": "PENDING"
    }
    step_number = 1

    # stream_mode="updates" yields the state delta committed at each superstep boundary
    for update in app_graph.stream(initial_state, stream_mode="updates"):
        print(f"\n--- [Superstep {step_number} Committed] ---")
        for node_name, state_delta in update.items():
            print(f"  * Node [{node_name}] committed delta: {state_delta}")
        step_number += 1