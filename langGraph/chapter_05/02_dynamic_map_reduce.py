import operator
import sys
from pathlib import Path
from typing import TypedDict, Annotated

from dotenv import load_dotenv, find_dotenv
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.types import Send
from loguru import logger

from graph_utils import print_graph_mermaid

load_dotenv(find_dotenv())
# Layer 1: Schema Definitions
class DishItem(TypedDict):
    dish_id:str
    dish_name:str
    quantity:int
class DishInspectionReport(TypedDict):
    dish_name:str
    status:str
    prep_time_minutes:int
    stock_confirmed:bool

class OrderMasterState(TypedDict):
    order_id:str
    items:list[DishItem]
    # Reducer channel: collects concurrent reports from N workers without conflicts!
    inspection_reports:Annotated[list[DishInspectionReport],operator.add] # ‼️‼️
    overall_status:str
    estimated_total_prep_time:int

# Principle of Least Privilege ✅
class WorkerTaskState(TypedDict):
    """Sub-state passed exclusively to an individual worker."""
    item:DishItem
 # Layer 2: Business Logic Nodes
def order_intake_node(state:OrderMasterState):
    return {"overall_status":"PROCESSING"}

def dispatch_dish_workers(state:OrderMasterState)->list[Send]:
    """
       ✅：     Dynamic Conditional Edge (Map phase):
            Generates N Send objects based on the dynamic size of state['items'].
    """
    sends = []
    for item in state["items"]:
        sends.append(Send("dish_inspector",{"item":item})) #❌❌❌
    logger.info(f"[Dispatcher] Generated {len(sends)} dynamic Send tasks for concurrent execution.")
    return sends

def dish_inspector_node(state:WorkerTaskState):
    """
            Individual Worker Node:
            Simulates inventory check, allergen verification, and kitchen prep time calculation.
    """
    item = state["item"]
    dish_name = item["dish_name"]
    qty = item["quantity"]
    logger.info(f"  [Worker Running] Inspecting inventory for: {dish_name} (Qty: {qty})")

    # Business rule: simulate prep time and inventory status
    prep_time = 15 if "Steak" in dish_name else 8
    report: DishInspectionReport = {
        "dish_name": dish_name,
        "status": "APPROVED",
        "prep_time_minutes": prep_time,
        "stock_confirmed": True
    }
    # Writes back to the aggregated 'inspection_reports' list via operator.add
    return {"inspection_reports": [report]}

# summary
def order_summary_node(state:OrderMasterState):
    reports = state["inspection_reports"]
    # calcute the max prep time for a dish
    max_prep_time = max(r["prep_time_minutes"] for r in reports)
    return{
        "overall_status": "ORDER_CONFIRMED",
        "estimated_total_prep_time": max_prep_time
    }

# generate a graph
def build_dynamic_order_graph():
    builder = StateGraph(OrderMasterState)
    builder.add_node("order_intake",order_intake_node)
    builder.add_node("dish_inspector",dish_inspector_node)
    builder.add_node("order_summary",order_summary_node)

    builder.add_edge(START,"order_intake")
    builder.add_conditional_edges("order_intake",dispatch_dish_workers,["dish_inspector"])
    builder.add_edge("dish_inspector","order_summary")
    builder.add_edge("order_summary",END)
    return builder.compile()

if __name__ == "__main__":
        app = build_dynamic_order_graph()
        # print_graph_mermaid(app,"02")

        # Dynamic order with 3 different dishes of varying complexity
        sample_order = {
            "order_id": "SKY-DINE-2026-X8",
            "items": [
                {"dish_id": "D101", "dish_name": "Wagyu Ribeye Steak", "quantity": 2},
                {"dish_id": "D102", "dish_name": "Truffle Mashed Potatoes", "quantity": 1},
                {"dish_id": "D103", "dish_name": "Wild Mushroom Soup", "quantity": 3}
            ],
            "inspection_reports": [],
            "overall_status": "NEW",
            "estimated_total_prep_time": 0
        }
        result = app.invoke(sample_order)
        logger.info("\n=== Final Master Order Summary ===")
        logger.info(f"Order ID: {result['order_id']}")
        logger.info(f"Overall Status: {result['overall_status']}")
        logger.info(f"Calculated Max Kitchen Prep Time: {result['estimated_total_prep_time']} mins")
        logger.info(f"Total Dispatches Completed: {len(result['inspection_reports'])}")
        for r in result["inspection_reports"]:
            logger.info(f"  • {r['dish_name']:<25} | Status: {r['status']} | Prep: {r['prep_time_minutes']} mins")

        ### 三、带注释的完整对照代码

        # 以后看这几个字段时，脑海里可以带入这个画面：
        #
        # # 1. 顾客下的单（包含 3 道菜）
        # OrderMasterState["items"] = [牛排, 土豆泥, 蘑菇汤]
        #
        # # 2. 条件边将 3 道菜拆成 3 张独立的 WorkerTaskState，派发给 3 个厨师
        # Send("dish_inspector", {"item": 牛排})
        # Send("dish_inspector", {"item": 土豆泥})
        # Send("dish_inspector", {"item": 蘑菇汤})
        #
        # # 3. 三个厨师并发检查完毕，报告自动汇集到 OrderMasterState["inspection_reports"]
        # OrderMasterState["inspection_reports"] = [
        #     {"dish_name": "牛排", "prep_time_minutes": 15, "stock_confirmed": True},
        #     {"dish_name": "土豆泥", "prep_time_minutes": 8, "stock_confirmed": True},
        #     {"dish_name": "蘑菇汤", "prep_time_minutes": 8, "stock_confirmed": True}
        # ]
        #
        # # 4. 汇总节点算出最慢需要 15 分钟，确认订单！
        # OrderMasterState["overall_status"] = "ORDER_CONFIRMED"
        # OrderMasterState["estimated_total_prep_time"] = 15