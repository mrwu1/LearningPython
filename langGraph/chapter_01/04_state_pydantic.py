"""
Lesson 1.4: Official Multi-Schema Graph Architecture (Pydantic V2 + TypedDict).
Key Objectives:
1. Input boundary validation via Pydantic V2 (input_schema).
2. Frictionless partial updates & reducers via TypedDict (state_schema).
3. Sanitized outbound projection via Pydantic V2 (output_schema).
"""

import operator
import sys
from pathlib import Path
from typing import Annotated, TypedDict
from pydantic import BaseModel, Field
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from graph_utils import print_graph_mermaid

# Ensure parent directory is in sys.path for shared utilities
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ==========================================
# 1. External Inbound Schema (Pydantic V2)
# ==========================================
class OrderInputRequest(BaseModel):
    order_id: str = Field(..., pattern=r"^SKY-[A-Z0-9]+$", description="Valid enterprise order ID")
    total_price: float = Field(..., gt=0.0, description="Price must be strictly positive")
    items: list[str] = Field(..., min_length=1, description="Order must contain at least 1 item")


# ==========================================
# 2. Internal Graph State (TypedDict)
# ==========================================
class OrderInternalState(TypedDict):
    order_id: str
    total_price: float
    items: list[str]
    # Internal scratchpad fields (not exposed to client)
    internal_risk_score: float
    audit_trail: Annotated[list[str], operator.add]
    order_status: str


# ==========================================
# 3. External Outbound Schema (Pydantic V2)
# Field names must match corresponding keys in OrderInternalState
# ==========================================
class OrderOutputResponse(BaseModel):
    order_id: str
    total_price: float
    order_status: str
    # internal_risk_score and audit_trail are automatically filtered out


# ==========================================
# 4. Compute Nodes
# ==========================================
def risk_assessment_node(state: OrderInternalState) -> dict:
    """Internal Worker: Computes proprietary risk score."""
    print(f"\n[RiskNode] Assessing internal risk for: {state['order_id']}")
    score = 15.0 if state["total_price"] < 100 else 75.0
    return {
        "internal_risk_score": score,
        "audit_trail": [f"[RiskNode] Computed internal risk: {score}"]
    }


def discount_and_finalize_node(state: OrderInternalState) -> dict:
    """Internal Worker: Applies promotional pricing and marks order ready."""
    discounted = state["total_price"] * 0.9 if state["internal_risk_score"] < 50 else state["total_price"]
    print(f"[FinalizeNode] Calculated final price: ${discounted:.2f}")
    return {
        "total_price": discounted,
        "order_status": "CONFIRMED",
        "audit_trail": ["[FinalizeNode] Finalized with status CONFIRMED"]
    }


# ==========================================
# 5. Graph Assembly
# ==========================================
def build_official_multi_schema_graph():
    # Pass input_schema and output_schema directly into the constructor
    builder = StateGraph(
        OrderInternalState,
        input_schema=OrderInputRequest,
        output_schema=OrderOutputResponse
    )

    builder.add_node("risk_assessment", risk_assessment_node)
    builder.add_node("finalize", discount_and_finalize_node)

    builder.add_edge(START, "risk_assessment")
    builder.add_edge("risk_assessment", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()


# ==========================================
# 6. Verification
# ==========================================
if __name__ == "__main__":
    app = build_official_multi_schema_graph()

    client_payload = {
        "order_id": "SKY-VIP999",
        "total_price": 88.0,
        "items": ["Singapore Laksa"]
    }

    final_response = app.invoke(client_payload)

    print("\n" + "=" * 60)
    print("Client Receives (Sanitized Output):")
    print(f"  Type: {type(final_response)}")
    print(f"  Payload: {final_response}")
    print("=" * 60)
    print_graph_mermaid(app, "04")