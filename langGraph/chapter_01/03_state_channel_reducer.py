import operator
from pprint import pprint
from typing import TypedDict, Annotated

from langgraph.constants import START, END
from langgraph.graph import StateGraph

from graph_utils import print_graph_mermaid


# 1. Custom Reducer for Dictionaries
# Rule: A reducer takes (current_value, update_value) and returns the merged result.
#✅
def merge_dict_reducer(current_dict:dict,update_dict:dict)->dict:
    merged = current_dict.copy() if current_dict else {}
    if update_dict:
        merged.update(update_dict)
    return merged

# 2. Define State Schema with Reducers
# Rule: Use Annotated[Type, ReducerFunction] to declare channel merge behavior.
class ComplianceOrderState(TypedDict):
    order_id:int
    # Channel with list concatenation reducer: multiple nodes can append simultaneously
    audit_logs: Annotated[list[str],operator.add]
    # Channel with custom dict merge reducer: multiple nodes can set sub-keys simultaneously
    service_metadata: Annotated[dict,merge_dict_reducer] # refer to ✅
    # Standard single-value channel (will overwrite if written sequentially)
    final_status:str

# 3. Define Parallel Compute Nodes
    # Both nodes will execute in parallel in the exact same Superstep,
    # writing to the EXACT SAME keys (audit_logs & service_metadata).
def security_scan_node(state: ComplianceOrderState) -> dict:
        """Parallel Worker 1: Scans for prohibited ingredients and fraud risk."""
        return {
            # Emits a partial list update
            "audit_logs": ["[SecurityScan] Anti-fraud check PASSED (Score: 0.98)"],
            # Emits a partial dict update
            "service_metadata": {"fraud_check_timestamp": "2026-10-17T13:30:00Z"}
        }

def regulatory_compliance_node(state: ComplianceOrderState) -> dict:
        """Parallel Worker 2: Verifies food tax laws and regional packaging rules."""
        return {
            # Emits another partial list update concurrently!
            "audit_logs": ["[Regulatory] Food tax compliance verified (Rate: 6%)"],
            # Emits another partial dict update concurrently!
            "service_metadata": {"tax_code": "TAX-FOOD-REG-01"}
        }

def finalize_order_node(state: ComplianceOrderState) -> dict:
        """Superstep 2: Aggregates all merged audit trails and finalizes state."""
        return {"final_status": "APPROVED_AND_CERTIFIED"}

# 4. Graph Assembly
def build_compliance_graph():
    builder = StateGraph(ComplianceOrderState)

    builder.add_node("scan",security_scan_node)
    builder.add_node("compliance",regulatory_compliance_node)

    builder.add_node("finalize",finalize_order_node)

    builder.add_edge(START,"scan")
    builder.add_edge(START,"compliance")

    builder.add_edge("scan","finalize")
    builder.add_edge("compliance","finalize")

    builder.add_edge("finalize",END)

    return builder.compile()

#test
if __name__=="__main__":
    app = build_compliance_graph()
    print_graph_mermaid(app,"reducer")

    initial_state: ComplianceOrderState = {
        "order_id": "ORD-SECURITY-101",
        "audit_logs": ["[Initial] Order received by gateway."],
        "service_metadata": {"env": "production"},
        "final_status": "PENDING"
    }
    #At key 'audit_logs': Can receive only one value per step. Use an Annotated key to handle multiple values.
    final_output = app.invoke(initial_state)
    print(f"final: {final_output}")