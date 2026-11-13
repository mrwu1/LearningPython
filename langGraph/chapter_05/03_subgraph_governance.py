"""
================================================================================
【LangGraph 阶段五：高阶流控与人机协同】第 3 课：大型微服务子图治理（Subgraph Governance）
================================================================================
【核心学习目标】：
1. 掌握子图治理（Subgraph Governance）工程架构：
   - 为什么大系统不能把所有逻辑塞进一张全局大图？（防止状态爆炸与强耦合）。
   - 主图（MainOrderGraph）负责全局调度与履约编排；
   - 子图（RiskAuditSubgraph）充当高度内聚的风控审计沙盒微服务。
2. 掌握状态隔离与无损通讯：
   - 私有字段（如 `device_trust_score` 设备评分）只在子图内流转，绝对不污染主图状态！
   - 公共契约字段（如 `risk_verdict`、`risk_summary`）在子图执行完后安全同步回主图。
3. 掌握 Compiled Graph 作为一等公民节点：
   - `parent_builder.add_node("risk_audit_subgraph", risk_subgraph)`
   - 父图直接将编译好的子图挂载为普通节点，条件边根据子图产出的结论分流。
4. 深入验证检查点命名空间 `checkpoint_ns` 对父子图的隔离保护。
================================================================================
"""

import sys
from pathlib import Path
from typing import TypedDict, Literal

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from loguru import logger

from graph_utils import print_graph_mermaid


# ==============================================================================
# 第一部分：风控审计子图（Risk Audit Subgraph）
# ==============================================================================

# 【子图私有状态契约】：
# 包含只有风控团队关心的设备可信度、信用分等高度机密字段
class RiskSubState(TypedDict):
    # 来自主图透传的入参字段
    user_id: str
    order_amount: float

    # --- 子图内部私有计算字段（主图根本没有定义它们，不会被泄露或污染） ---
    device_trust_score: int    # 设备环境指纹可信度（0-100）
    user_credit_score: int     # 用户历史履约信用分

    # --- 子图对外公开的裁决契约（主图定义了同名字段，会自动同步回主图） ---
    risk_verdict: str          # 终审裁决: "APPROVED"（通过）或 "FLAGGED"（风控拦截）
    risk_summary: str          # 详细风控报告摘要


def verify_device_node(state: RiskSubState) -> dict:
    """【子图步骤 1】：核查设备环境指纹、代理 IP 与作弊插件。"""
    logger.info(f"  [子图节点: 设备核查] 正在检测用户 {state['user_id']} 的设备指纹安全风险...")
    # VIP 用户设备加分，普通用户默认评分
    score = 92 if "VIP" in state["user_id"] else 45
    return {"device_trust_score": score}


def compute_risk_decision_node(state: RiskSubState) -> dict:
    """【子图步骤 2】：综合内部设备评分与订单金额，计算最终裁决。"""
    trust = state["device_trust_score"]
    amount = state["order_amount"]
    logger.info(f"  [子图节点: 风险决策] 综合评估: 设备可信度={trust}, 订单金额=${amount:,.2f}")

    # 业务规则：设备可信度 >= 50 且金额 <= 500 则自动准许通过
    if trust >= 50 and amount <= 500:
        return {
            "risk_verdict": "APPROVED",
            "risk_summary": f"合规订单。设备可信度 {trust} 分，符合准入标准。"
        }
    else:
        return {
            "risk_verdict": "FLAGGED",
            "risk_summary": f"高风险预警！设备可信度不足（{trust}分）或金额超限（${amount:,.2f}）。"
        }


def build_risk_subgraph():
    """编译并产出风控审计子图运行时。"""
    sub_builder = StateGraph(RiskSubState)
    sub_builder.add_node("device_check", verify_device_node)
    sub_builder.add_node("risk_decision", compute_risk_decision_node)

    sub_builder.add_edge(START, "device_check")
    sub_builder.add_edge("device_check", "risk_decision")
    sub_builder.add_edge("risk_decision", END)

    return sub_builder.compile()


# ==============================================================================
# 第二部分：主订单履约图（Main Order Pipeline）
# ==============================================================================

# 【主图全局状态契约】：
# 只包含全局主链路所需的订单号、金额、履约状态以及子图回传的公共风控结论
class MainOrderState(TypedDict):
    user_id: str
    order_id: str
    order_amount: float
    
    # 由风控子图计算并写回的公共字段
    risk_verdict: str
    risk_summary: str

    # 后续外卖主流程履约字段
    fulfillment_status: str


def order_intake_node(state: MainOrderState) -> dict:
    """【主图步骤 1】：接收主订单并建单。"""
    print(f"\n---> [主图节点: 订单受理] 收到新订单: {state['order_id']}, 提交风控子图审查...")
    return {"fulfillment_status": "INTAKE_COMPLETED"}


def route_order_fulfillment(state: MainOrderState) -> Literal["fulfill_order", "abort_order"]:
    """
    【主图动态路由】：
    根据风控子图执行完毕后写回的 risk_verdict 动态选择主链路走向：
    - APPROVED -> 走向外卖出餐发货
    - FLAGGED  -> 走向反欺诈拦截与取消订单
    """
    if state["risk_verdict"] == "APPROVED":
        return "fulfill_order"
    return "abort_order"


def fulfill_order_node(state: MainOrderState) -> dict:
    """【主图步骤 3a】：风控合格，推单至商家后厨制作并调度骑手。"""
    logger.info(f"🚀 [主图节点: 履约出餐] 成功！订单 {state['order_id']} 已派发至商家后厨开始烹饪。")
    return {"fulfillment_status": "DELIVERED_TO_KITCHEN"}


def abort_order_node(state: MainOrderState) -> dict:
    """【主图步骤 3b】：风控拦截，自动关闭订单并冻结账户。"""
    logger.warning(f"🛑 [主图节点: 安全拦截] 拦截成功！订单 {state['order_id']} 已取消。原因: {state['risk_summary']}")
    return {"fulfillment_status": "CANCELLED_FRAUD_DETECTED"}


def build_master_pipeline():
    # 1. 获取编译好的子图
    risk_subgraph = build_risk_subgraph()

    parent_builder = StateGraph(MainOrderState)
    parent_builder.add_node("intake", order_intake_node)

    # 2. 【核心架构：将已编译的子图直接作为一等公民节点挂载！】
    parent_builder.add_node("risk_audit_subgraph", risk_subgraph)
    parent_builder.add_node("fulfill_order", fulfill_order_node)
    parent_builder.add_node("abort_order", abort_order_node)

    # 3. 编排主图拓扑
    parent_builder.add_edge(START, "intake")
    parent_builder.add_edge("intake", "risk_audit_subgraph")

    # 4. 根据子图的产出执行条件分流
    parent_builder.add_conditional_edges(
        "risk_audit_subgraph",
        route_order_fulfillment
    )

    parent_builder.add_edge("fulfill_order", END)
    parent_builder.add_edge("abort_order", END)

    checkpointer = MemorySaver()
    return parent_builder.compile(checkpointer=checkpointer)


# ==============================================================================
# 第三部分：双场景验证与状态防污染审查
# ==============================================================================
if __name__ == "__main__":
    app = build_master_pipeline()
    print_graph_mermaid(app, "03_subgraph_governance")

    # --------------------------------------------------------------------------
    # 场景 1：白名单合规 VIP 订单（预期顺利通过风控并推单后厨）
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("【测试场景 1】：白名单 VIP 正常订单...")
    vip_order = {
        "order_id": "ORD-VIP-001",
        "user_id": "USER_VIP_ALEX",
        "order_amount": 120.00,
        "risk_verdict": "",
        "risk_summary": "",
        "fulfillment_status": "NEW"
    }
    config_vip = {"configurable": {"thread_id": "SESSION_ORDER_VIP_001"}}
    res_vip = app.invoke(vip_order, config=config_vip)

    print("\n🔎 【状态防污染核验 (State Encapsulation)】:")
    print(f"  • 主图最终状态包含的键: {list(res_vip.keys())}")
    print(f"  • 子图的私有字段 'device_trust_score' 是否泄露到主图: {'device_trust_score' in res_vip}")
    print(f"  • 最终履约状态: {res_vip['fulfillment_status']}")
    print(f"  • 风控审计报告: {res_vip['risk_summary']}")

    # --------------------------------------------------------------------------
    # 场景 2：可疑大额匿名订单（预期被子图识别并在主图中安全拦截）
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("【测试场景 2】：可疑高风险大额订单...")
    sketchy_order = {
        "order_id": "ORD-SKETCH-002",
        "user_id": "USER_ANON_GUEST",
        "order_amount": 999.00,  # 严重超标
        "risk_verdict": "",
        "risk_summary": "",
        "fulfillment_status": "NEW"
    }
    config_sketch = {"configurable": {"thread_id": "SESSION_ORDER_SKETCH_002"}}
    res_sketch = app.invoke(sketchy_order, config=config_sketch)

    print(f"\n  • 最终履约状态: {res_sketch['fulfillment_status']}")
    print(f"  • 拦截详细原因: {res_sketch['risk_summary']}")
    print("=" * 65)
