"""
================================================================================
【LangGraph 阶段一：基础状态机内核】第 2 课：Pregel 并发扇出与汇聚（Fan-Out & Fan-In）
================================================================================
【核心学习目标】：
1. 理解 Google Pregel 计算模型：超步（Superstep）的概念。
2. 掌握扇出并发（Fan-Out）：一个上游节点同时连接多个下游节点，底层并行调度执行。
3. 掌握扇入汇聚（Fan-In）：多个并行节点收敛汇总到一个节点，等待所有上游执行完毕后才触发。
4. 掌握无锁隔离原则：当多个并行节点只写入各自独立的字段时，默认的 LastValue 通道即可安全工作。
5. 掌握 stream(..., stream_mode="updates")：观察每一个超步（Superstep）的状态增量变化。
================================================================================
"""

import sys
from pathlib import Path
from typing import TypedDict

# 自动将项目根目录加入 sys.path，防止多层目录下导包失败
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.constants import START, END
from langgraph.graph import StateGraph

from graph_utils import print_graph_mermaid


# ==============================================================================
# 第一步：定义并发业务状态（State Schema）
# ==============================================================================
# 【无锁并发设计原则】：
# 当多个节点在同一个超步中并行执行时，若它们各自只修改【互不重叠】的独立字段，
# LangGraph 可以在完全不需要 Reducer 合并器的情况下自动安全合并！
class OrderProcessingState(TypedDict):
    order_id: str
    items: list[str]
    
    # --- 下面三个字段分别由三个独立的并行计算节点更新，互不冲突 ---
    inventory_available: bool  # 由 inventory_check_node 更新（库存是否足够）
    assigned_rider_id: str     # 由 rider_dispatch_node 更新（分配的外卖骑手 ID）
    discount_amount: float     # 由 coupon_eval_node 更新（优惠券折扣金额）

    # --- 最终汇聚结果 ---
    final_verdict: str         # 由 order_summary_node 聚合裁决最终状态


# ==============================================================================
# 第二步：定义各个计算节点
# ==============================================================================

def dispatch_node(state: OrderProcessingState) -> dict:
    """
    【中心调度节点（起点）】：
    订单接单后，将状态置为 PROCESSING，随后触发后续三个维度的并行检查。
    """
    print("\n---> [Superstep 1] 调度中心开始分发任务...")
    return {"final_verdict": "PROCESSING"}


# --- 以下三个节点将在同一个 Superstep 中被 Pregel 引擎并行调度 ---

def inventory_check_node(state: OrderProcessingState) -> dict:
    """【并行工作者 1】：模拟微服务仓储库存核验。"""
    print("  * [Parallel Worker: Inventory] 检查商品库存 -> 充足")
    return {"inventory_available": True}


def rider_dispatch_node(state: OrderProcessingState) -> dict:
    """【并行工作者 2】：模拟基于地理位置调度就近骑手。"""
    matched_rider = "RIDER-9527"
    print(f"  * [Parallel Worker: Rider] 算法调度匹配骑手 -> {matched_rider}")
    return {"assigned_rider_id": matched_rider}


def coupon_eval_node(state: OrderProcessingState) -> dict:
    """【并行工作者 3】：模拟营销系统计算满减与优惠券。"""
    discount = 15.50
    print(f"  * [Parallel Worker: Coupon] 营销核算优惠减免 -> ${discount}")
    return {"discount_amount": discount}


# --- 聚合收敛节点 ---

def order_summary_node(state: OrderProcessingState) -> dict:
    """
    【汇聚决策节点（终点前哨）】：
    【关键机制】：只有在 inventory、rider、coupon 全部执行完毕后，当前节点才会被唤醒！
    它能同时看到前面三个并行节点各自写入最新结果的完整 State。
    """
    print("\n---> [Superstep 3] 汇总所有并行结果，进行最终裁决...")
    is_ready = state["inventory_available"] and bool(state["assigned_rider_id"])
    verdict = (
        f"CONFIRMED (Courier: {state['assigned_rider_id']}, Saved: ${state['discount_amount']:.2f})"
        if is_ready else "REJECTED"
    )
    return {"final_verdict": verdict}


# ==============================================================================
# 第三步：构建扇出（Fan-Out）与扇入（Fan-In）图拓扑
# ==============================================================================
def build_pregel_demo_graph():
    builder = StateGraph(OrderProcessingState)

    # 1. 注册所有节点
    builder.add_node("dispatch", dispatch_node)
    builder.add_node("inventory", inventory_check_node)
    builder.add_node("rider", rider_dispatch_node)
    builder.add_node("coupon", coupon_eval_node)
    builder.add_node("summary", order_summary_node)

    # 2. 初始入口
    builder.add_edge(START, "dispatch")

    # 3. 【核心知识点：扇出（Fan-Out）】
    # 从同一个源节点 dispatch 发出三条静态边，分别指向三个不同的下游节点！
    # 底层效果：Pregel 调度器发现三个节点同时就绪，将在同一个超步里并发执行它们！
    builder.add_edge("dispatch", "inventory")
    builder.add_edge("dispatch", "rider")
    builder.add_edge("dispatch", "coupon")

    # 4. 【核心知识点：扇入（Fan-In / Barrier Synchronization 屏障同步）】
    # 三个并行节点全部把出边连向 summary 节点！
    # 底层效果：Pregel 会自动充当同步屏障，严格等待这三个节点全部产生增量提交后，才启动 summary 节点！
    builder.add_edge("inventory", "summary")
    builder.add_edge("rider", "summary")
    builder.add_edge("coupon", "summary")

    # 5. 汇聚节点结束后连向 END
    builder.add_edge("summary", END)

    # 6. 编译图
    return builder.compile()


# ==============================================================================
# 第四步：测试与运行观察（Stream Updates）
# ==============================================================================
if __name__ == "__main__":
    app_graph = build_pregel_demo_graph()

    # 打印可视化架构图
    print_graph_mermaid(app_graph, "02")

    initial_state: OrderProcessingState = {
        "order_id": "ORD-20261017-888",
        "items": ["Cheese Pizza", "Cold Cola"],
        "inventory_available": False,
        "assigned_rider_id": "",
        "discount_amount": 0.0,
        "final_verdict": "PENDING"
    }

    step_number = 1
    print("\n========== 开始通过 stream_mode='updates' 观察超步执行 ==========")
    
    # 【核心调试技巧】：
    # stream_mode="updates" 会在每个超步（Superstep）执行边界向外 yield 本轮发生变化的状态增量字典。
    # - Superstep 1: dispatch 提交
    # - Superstep 2: inventory, rider, coupon 并发执行并在同一步提交三个增量
    # - Superstep 3: summary 汇总提交
    for update in app_graph.stream(initial_state, stream_mode="updates"):
        print(f"\n--- [Superstep {step_number} 提交完成 (Committed)] ---")
        for node_name, state_delta in update.items():
            print(f"  * 节点 [{node_name}] 写入增量: {state_delta}")
        step_number += 1
