from pprint import pprint
from typing import TypedDict, Literal

from langgraph.graph import StateGraph, START, END

from graph_utils import print_graph_mermaid


class OrderState(TypedDict):
    order_id: int
    items:list[str]
    total_price:float
    risk_score:float
    retry_count:int
    status:str

 # ==========================================
    # 2. Define Compute Nodes
    # Rule: Nodes are pure functions receiving the current State
    # and returning a dictionary of partial updates.
    # ==========================================
def validate_node(state:OrderState)->dict:
    if state['total_price']>100.00:
        calculated_risk =85.0
    else:
        calculated_risk = 20.0
    return  {
            "risk_score": calculated_risk,
            "status": "VALIDATED"
    }

def auto_fix_node(state:OrderState)->dict:
    current_retry = state["retry_count"]+1
    # Apply a 30% discount to reduce exposure and pass risk checks
    new_price = state["total_price"] *0.7

    return {
        "total_price": new_price,
        "retry_count": current_retry,
        "status": "AUTO_FIXED"
    }
 # ==========================================
    # 3. Define Conditional Routing Edge
    # Rule: Returns the name of the next target node or the special END constant.
    # ==========================================

def should_continue(state:OrderState)->Literal["auto_fix",END]:
    if state['risk_score']<60.0:
        if state['retry_count']<2:
            return "auto_fix"
        else:
            return END
    return END
  # ==========================================
    # 4. Graph Assembly and Compilation
    # ==========================================
def build_order_graph():
    builder = StateGraph(OrderState,"01")

    builder.add_node("validate",validate_node)
    builder.add_node("auto_fix",auto_fix_node)

    builder.add_edge(START,"validate")

    builder.add_conditional_edges(
        source="validate",
        path=should_continue,
        path_map={
            "auto_fix":"auto_fix",
            END:END
        }
    )
    # Cyclic edge: After auto_fix, loop back to validate
    builder.add_edge("auto_fix","validate")
    # 4. Compile into an executable StateGraph runtime
    app = builder.compile()
    return app
  # ==========================================
    # 5. Execution and Verification
    # ==========================================

if __name__ == "__main__":
    app = build_order_graph()
    # 只需要这一行！
    print_graph_mermaid(app)

    # Initial input state: Price $180 triggers risk assessment and loops
    initial_order: OrderState = {
        "order_id": "SKY-20261017-001",
        "items": ["Tomahawk Steak", "Vintage Red Wine"],
        "total_price": 180.0,
        "risk_score": 0.0,
        "retry_count": 0,
        "status": "CREATED"
    }
    final_state = app.invoke(initial_order)
    pprint(f"final_state:{final_state}")
