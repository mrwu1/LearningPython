"""
================================================================================
【LangGraph 阶段五：高阶流控与人机协同】第 2 课：动态分发与 Map-Reduce 并行算子（Send API）
================================================================================
【核心学习目标】：
1. 掌握动态扇出（Dynamic Fan-Out / Map-Reduce）：
   - 静态图只能连接固定数量的边；
   - 当任务数量是【动态不确定】的（例如根据用户订单里点了 3 道菜还是 10 道菜动态分发）时，必须使用 `langgraph.types.Send`！
2. 掌握 `Send(node_name, payload)` 的核心用法：
   - 条件路由边返回 `list[Send]`；
   - LangGraph 底层为每个 Send 对象并发拉起一个独立执行的 worker 任务实例。
3. 掌握最小权限原则（Principle of Least Privilege）：
   - 每一个 Worker 节点不需要看到庞大的主状态 `OrderMasterState`，只需接收精简的子状态 `WorkerTaskState`。
4. 掌握 Reduce 阶段：
   - 借助 `Annotated[list, operator.add]`，N 个并发 worker 产生的报告无冲突汇聚回主状态。
================================================================================
"""

import operator
import sys
from pathlib import Path
from typing import TypedDict, Annotated

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.types import Send
from loguru import logger

from graph_utils import print_graph_mermaid


# ==============================================================================
# 第一步：定义主状态与工作子状态（Schema Definitions）
# ==============================================================================

# 基础菜品条目
class DishItem(TypedDict):
    dish_id: str
    dish_name: str
    quantity: int


# 单个菜品并行质检报告
class DishInspectionReport(TypedDict):
    dish_name: str
    status: str
    prep_time_minutes: int
    stock_confirmed: bool


# 【主图全局状态（Master State）】：
class OrderMasterState(TypedDict):
    order_id: str
    items: list[DishItem]  # 订单菜品清单（长度动态未知）
    
    # 【核心 Reducer 聚合通道】：
    # 挂载 operator.add，承接后续 N 个动态 worker 并发提交的检查报告，自动追加合并
    inspection_reports: Annotated[list[DishInspectionReport], operator.add]
    
    overall_status: str
    estimated_total_prep_time: int


# 【Worker 独立任务子状态（最小权限原则）】：
# 每个 worker 只需要知道自己要检查哪一道菜，不需要知道整个订单的其他细节
class WorkerTaskState(TypedDict):
    item: DishItem


# ==============================================================================
# 第二步：定义计算节点与动态分发器（Map Phase）
# ==============================================================================

def order_intake_node(state: OrderMasterState) -> dict:
    """【订单接单节点】：标记状态为 PROCESSING，准备拆单分发。"""
    print(f"\n---> [Node: order_intake] 收到大订单 {state['order_id']}，包含 {len(state['items'])} 道菜品")
    return {"overall_status": "PROCESSING"}


# ==============================================================================
# 【核心机制：动态 Map 分发路由函数】
# ==============================================================================
# 路由函数不再返回单个节点名称，而是返回一个包含多个 Send 对象的 list！
# 签名：state -> list[Send]
def dispatch_dish_workers(state: OrderMasterState) -> list[Send]:
    """
    【动态派单员（Map 阶段）】：
    - 遍历订单中的每一道菜品；
    - 为每一道菜动态生成一个 Send("目标节点名", 子任务载荷)；
    - 底层 Pregel 调度器会立刻并发启动对应数量的 worker 任务！
    """
    sends = []
    for item in state["items"]:
        # Send 第一个参数是目标节点名 "dish_inspector"，第二个参数是传给该节点的专用子状态
        sends.append(Send("dish_inspector", {"item": item}))

    print(f"\n⚡ [Map 动态派发] 根据菜品数量，动态生成了 {len(sends)} 个并发审查任务！")
    return sends


def dish_inspector_node(state: WorkerTaskState) -> dict:
    """
    【单个菜品质检节点（Worker 节点）】：
    - 接收子状态 WorkerTaskState；
    - 并行核查库存与估算备餐时间；
    - 返回 {"inspection_reports": [report]}，由 operator.add 自动汇聚。
    """
    item = state["item"]
    dish_name = item["dish_name"]
    qty = item["quantity"]
    print(f"  🍳 [并发厨师] 开始核检菜品: {dish_name} (数量: {qty})")

    # 业务模拟：牛排类备餐慢需要 15 分钟，其他菜品 8 分钟
    prep_time = 15 if "Steak" in dish_name or "牛排" in dish_name else 8

    report: DishInspectionReport = {
        "dish_name": dish_name,
        "status": "APPROVED",
        "prep_time_minutes": prep_time,
        "stock_confirmed": True
    }

    # 返回列表，触发全局主状态中的 operator.add 自动无锁归并
    return {"inspection_reports": [report]}


def order_summary_node(state: OrderMasterState) -> dict:
    """
    【汇总汇聚节点（Reduce 阶段）】：
    - 等待所有动态 worker 全部执行完毕（屏障同步）；
    - 汇总所有报告，计算整张订单后厨出餐的最长瓶颈时间（最大耗时）。
    """
    print("\n---> [Reduce 汇总节点] 所有菜品质检完成，正在计算整单后厨出品瓶颈...")
    reports = state["inspection_reports"]
    max_prep_time = max(r["prep_time_minutes"] for r in reports) if reports else 0
    return {
        "overall_status": "ORDER_CONFIRMED",
        "estimated_total_prep_time": max_prep_time
    }


# ==============================================================================
# 第三步：组装动态图拓扑
# ==============================================================================
def build_dynamic_order_graph():
    builder = StateGraph(OrderMasterState)

    builder.add_node("order_intake", order_intake_node)
    builder.add_node("dish_inspector", dish_inspector_node)
    builder.add_node("order_summary", order_summary_node)

    builder.add_edge(START, "order_intake")

    # 【核心条件路由：挂载 Map 分发器】
    # 第三个参数 ["dish_inspector"] 是声明该条件边可能会派发给哪个下游节点
    builder.add_conditional_edges(
        "order_intake",
        dispatch_dish_workers,
        ["dish_inspector"] #{"dish_inspector":"dish_inspector"}
    )

    # 汇聚到汇总节点
    builder.add_edge("dish_inspector", "order_summary")
    builder.add_edge("order_summary", END)

    return builder.compile()


# ==============================================================================
# 第四步：执行与验证
# ==============================================================================
if __name__ == "__main__":
    app = build_dynamic_order_graph()
    print_graph_mermaid(app, "02_dynamic_map_reduce")

    # 模拟一份包含 3 道不同耗时菜品的真实外卖单
    sample_order = {
        "order_id": "SKY-DINE-2026-X8",
        "items": [
            {"dish_id": "D101", "dish_name": "Wagyu Ribeye Steak (和牛肋眼牛排)", "quantity": 2},
            {"dish_id": "D102", "dish_name": "Truffle Mashed Potatoes (黑松露土豆泥)", "quantity": 1},
            {"dish_id": "D103", "dish_name": "Wild Mushroom Soup (野生菌菇汤)", "quantity": 3}
        ],
        "inspection_reports": [],
        "overall_status": "NEW",
        "estimated_total_prep_time": 0
    }

    print("\n========== 开始执行动态 Map-Reduce 订单系统 ==========")
    result = app.invoke(sample_order)

    print("\n" + "=" * 65)
    print("========== 最终订单核准汇总报告 ==========")
    print(f"  • 订单号: {result['order_id']}")
    print(f"  • 订单总状态: {result['overall_status']}")
    print(f"  • 预计整单出品耗时 (取决于最慢的菜品): {result['estimated_total_prep_time']} 分钟")
    print(f"  • 动态派发完成数: {len(result['inspection_reports'])} 道菜品全部核验通过")
    print("  • 各菜品明细:")
    for r in result["inspection_reports"]:
        print(f"    - {r['dish_name']:<35} | 状态: {r['status']} | 耗时: {r['prep_time_minutes']} 分钟")
    print("=" * 65)
