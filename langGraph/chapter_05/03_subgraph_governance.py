# 我们来构建真实的业务沙盒：《苍穹外卖·主订单履约与独立风控审计子图》。
#
# • 子图（RiskAuditSubgraph）：
    # • 维护独立的RiskSubState。
    # • 包含内部私有步骤：设备指纹检测 → 信用评分计算 → 判定风险等级。
    # • 私有字段：device_trust_score（设备可信度），这个字段绝对不会出现在主订单状态里！
    # • 对外输出契约：risk_verdict("APPROVED"
# • 主图（MainOrderGraph）：
    # • 维护 MainOrderState。
    # • 接收订单 → 调用风控子图 → 条件路由（风控通过则进入履约发货，否则取消订单）。
from typing import TypedDict, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from loguru import logger

from graph_utils import print_graph_mermaid


class RiskSubState(TypedDict):
    user_id:str
    order_amount:float
    #private internal fields
    device_trust_score:int
    user_credict_score:int
    #PUBLIC CONTRACT FIELDS
    risk_verdict:str
    risk_summary:str

class MainOrderState(TypedDict):
    user_id: str
    order_id: str
    order_amount: float
    # Fields populated by the Risk Subgraph
    risk_verdict: str
    risk_summary: str

    # Downstream fulfillment fields
    fulfillment_status: str

def verify_device_node(state: RiskSubState):
        """Internal Subgraph Step 1: Checks device fingerprint & IP reputation."""
        logger.info(f"  [Sub-node: DeviceCheck] Auditing device fingerprint for user: {state['user_id']}")
        # Simulating internal score calculation (higher is safer)
        score = 92 if "VIP" in state["user_id"] else 45
        return {"device_trust_score": score}


def compute_risk_decision_node(state: RiskSubState):
    """Internal Subgraph Step 2: Synthesizes private scores into public verdict."""
    trust = state["device_trust_score"]
    amount = state["order_amount"]
    logger.info(f"  [Sub-node: RiskDecision] Evaluating TrustScore={trust} against Amount=${amount:,.2f}")

    if trust >= 50 and amount <= 500:
        return {
            "risk_verdict": "APPROVED",
            "risk_summary": f"Clean order. Trust score {trust} satisfies audit standard."
        }
    else:
        return {
            "risk_verdict": "FLAGGED",
            "risk_summary": f"High risk! Suspicious device (Trust: {trust}) with Amount: ${amount:,.2f}."
        }

def build_risk_subgraph():
        """Builds and compiles the isolated Risk Audit Subgraph."""
        sub_builder = StateGraph(RiskSubState)
        sub_builder.add_node("device_check", verify_device_node)
        sub_builder.add_node("risk_decision", compute_risk_decision_node)

        sub_builder.add_edge(START, "device_check")
        sub_builder.add_edge("device_check", "risk_decision")
        sub_builder.add_edge("risk_decision", END)

        return sub_builder.compile()

# Layer 3: Parent Graph Construction (Orchestration Pipeline)
def order_intake_node(state: MainOrderState):
    """Parent Step 1: Ingests master order."""
    return {"fulfillment_status": "INTAKE_COMPLETED"}


def route_order_fulfillment(state: MainOrderState) -> Literal["fulfill_order", "abort_order"]:
    """Conditional Edge: Routes flow based on the Subgraph's verdict."""
    if state["risk_verdict"] == "APPROVED":
        return "fulfill_order"
    return "abort_order"


def fulfill_order_node(state: MainOrderState):
    """Parent Step 3a: Fulfills order and dispatches delivery."""
    logger.info(f"[Parent: Fulfillment] 🚀 Success! Order {state['order_id']} dispatched to kitchen.")
    return {"fulfillment_status": "DELIVERED_TO_KITCHEN"}


def abort_order_node(state: MainOrderState):
    """Parent Step 3b: Blocks fraudulent order."""
    logger.warning(f"[Parent: Security] 🛑 Intercepted! Order {state['order_id']} cancelled. Reason:{state['risk_summary']}")
    return {"fulfillment_status": "CANCELLED_FRAUD_DETECTED"}

def build_master_pipeline():
    risk_subgraph  = build_risk_subgraph()
    parent_builder = StateGraph(MainOrderState)

    parent_builder.add_node("intake", order_intake_node)

    #  ⚠️⚠️：EMBED THE COMPILED SUBGRAPH DIRECTLY AS A FIRST-CLASS NODE!
    parent_builder.add_node("risk_audit_subgraph", risk_subgraph)
    parent_builder.add_node("fulfill_order", fulfill_order_node)
    parent_builder.add_node("abort_order", abort_order_node)

    # Wire edges
    parent_builder.add_edge(START,"intake")
    parent_builder.add_edge("intake","risk_audit_subgraph")
    #  ⚠️⚠️ router: dynamic choose the next node
    parent_builder.add_conditional_edges("risk_audit_subgraph",route_order_fulfillment)
    parent_builder.add_edge("fulfill_order",END)
    parent_builder.add_edge("abort_order", END)

    checkpointer = MemorySaver()
    return parent_builder.compile(checkpointer=checkpointer)

if __name__ == "__main__":
        app = build_master_pipeline()
        print_graph_mermaid(app,"03")
        # Case 1: Legitimate VIP Order
        vip_order = {
            "order_id": "ORD-VIP-001",
            "user_id": "USER_VIP_ALEX",
            "order_amount": 120.00,
            "risk_verdict": "",
            "risk_summary": "",
            "fulfillment_status": "NEW"
        }
        config_vip = {"configurable":{"thread_id":"SESSION_ORDER_VIP1_001"}}
        res_vip= app.invoke(vip_order,config=config_vip)
        logger.info("\n--- Verification: Checking Parent State Pollution ---")
        logger.info(f"Parent State Keys: {list(res_vip.keys())}")
        logger.info(f"Is private 'device_trust_score' leaked into parent?: {'device_trust_score' in res_vip}")
        logger.info(f"Final Status: {res_vip['fulfillment_status']}")
        logger.info(f"Verdict Summary: {res_vip['risk_summary']}")

        # Case 2: Suspicious High-Risk Order
        logger.info("\n=== Scenario 2: Processing Suspicious Order ===")
        sketchy_order = {
            "order_id": "ORD-SKETCH-002",
            "user_id": "USER_ANON_GUEST",
            "order_amount": 999.00,
            "risk_verdict": "",
            "risk_summary": "",
            "fulfillment_status": "NEW"
        }
        config_sketch = {"configurable": {"thread_id": "SESSION_ORDER_SKETCH_002"}}
        res_sketch = app.invoke(sketchy_order, config=config_sketch)
        logger.info(f"Final Status: {res_sketch['fulfillment_status']}")
        logger.info(f"Verdict Summary: {res_sketch['risk_summary']}")

        # Case 3: Deep-Dive into Checkpointer Namespaces
        logger.info("\n=== Scenario 3: Inspecting Internal Subgraph Namespaces ===")
        all_checkpoints = list(app.checkpointer.list(config_vip))
        logger.info(f"Total checkpointer snapshots stored for VIP order: {len(all_checkpoints)}")
        for idx, cp in enumerate(all_checkpoints):
            ns = cp.config["configurable"].get("checkpoint_ns", "root")
            logger.info(f"  [{idx}] Namespace: {repr(ns):<45} | Channels: {list(cp.checkpoint['channel_values'].
                                                                                keys())}")