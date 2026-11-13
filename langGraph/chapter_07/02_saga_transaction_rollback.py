"""
================================================================================
【LangGraph 阶段七：生产高可用与分布式防御】第 2 课：Saga 分布式事务与逆向补偿回滚（Saga Rollback Pattern）
================================================================================
【核心学习目标】：
1. 掌握分布式微服务长事务解决方案：Saga 补偿模式（Saga Compensation Pattern）：
   - 核心痛点：智能体跨越多个异构微服务（仓储扣库存 -> 支付扣款 -> 骑手调度）；无法使用传统的单机 ACID 数据库事务；
   - 事故场景：如果骑手调度失败（例如暴雨无骑手），此前已扣减的库存和已支付的资金将变成脏数据留在系统中，造成客诉与对账不平！
2. 掌握 LIFO（后进先出）补偿栈设计：
   - 状态中定义 `compensation_stack: list[str]`；
   - 正向每成功一步（T1 锁库、T2 扣款），就向栈中压入一条逆向补偿意图（"ROLLBACK_INVENTORY"、"REFUND_PAYMENT"）；
   - 后续任何步骤抛出异常，条件路由立刻导向 Saga 补偿器节点（`saga_compensator`）；
   - 补偿器严格倒序弹出任务，依次执行原路退款与库存返还，保证最终业务数据零差异！
================================================================================
"""

import sys
from pathlib import Path
from typing import TypedDict, Literal
from dotenv import find_dotenv, load_dotenv
from loguru import logger

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(find_dotenv())

from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph


# ==============================================================================
# 第一层：模拟外部微服务物理数据库
# ==============================================================================
# 仓储库存微服务数据库（惠灵顿牛排初始库存 10 份）
warehouse_db = {"Wellington_Steak": 10}

# 财务钱包微服务数据库（用户账户余额初始 $100.00）
wallet_db = {"balance": 100.00}


# ==============================================================================
# 第二层：定义携带 Saga 补偿栈的状态契约（State Schema）
# ==============================================================================
class SagaOrderState(TypedDict):
    order_id: str
    dish_name: str
    amount: float
    
    # ==========================================================================
    # 【核心字段：Saga LIFO 补偿栈】
    # 按照严格时间顺序，依次记录每一个可逆向撤回的正向操作名称
    # 例如：["ROLLBACK_INVENTORY", "REFUND_PAYMENT"]
    # ==========================================================================
    compensation_stack: list[str]
    
    current_error: str         # 运行时记录的异常/错误原因
    order_disposition: str     # 最终履约处置结论


# ==============================================================================
# 第三层：正向业务计算节点（Forward Positive Actions）
# ==============================================================================

def reserve_inventory_node(state: SagaOrderState) -> dict:
    """【正向事务 T1：锁定库存】：向仓储微服务申请预扣 1 份牛排。"""
    dish = state["dish_name"]
    logger.info(f"[正向事务 T1: 锁定库存] 正在为菜品 {dish} 锁定库存...")

    if warehouse_db.get(dish, 0) <= 0:
        return {"current_error": "OUT_OF_STOCK"}

    # 执行物理锁库
    warehouse_db[dish] -= 1
    logger.info(f"  -> 库存锁定成功！仓储剩余库存: {warehouse_db[dish]}")

    # 将回滚动作压入补偿栈！
    new_stack = state.get("compensation_stack", []).copy()
    new_stack.append("ROLLBACK_INVENTORY")
    return {"compensation_stack": new_stack}


def deduct_payment_node(state: SagaOrderState) -> dict:
    """【正向事务 T2：资金扣款】：从用户钱包账户扣减订单金额。"""
    amount = state["amount"]
    logger.info(f"[正向事务 T2: 钱包扣款] 正在从用户钱包扣款: ${amount:,.2f} ...")

    if wallet_db["balance"] < amount:
        return {"current_error": "INSUFFICIENT_FUNDS"}

    # 执行真实资金扣款
    wallet_db["balance"] -= amount
    logger.info(f"  -> 资金扣除成功！钱包剩余余额: ${wallet_db['balance']:,.2f}")

    # 将资金退款动作压入补偿栈！
    new_stack = state["compensation_stack"].copy()
    new_stack.append("REFUND_PAYMENT")
    return {"compensation_stack": new_stack}


def dispatch_courier_node(state: SagaOrderState) -> dict:
    """
    【正向事务 T3：调度三方骑手】：调用美团/顺丰第三方物流配送接口。
    故意模拟外部突发灾难故障（如暴雨天气周边无骑手接单，返回 503 错误）。
    """
    logger.info("[正向事务 T3: 调度骑手] 正在调用美团/顺丰智能运力调度系统...")
    logger.error("  ❌ [三方接口 503 异常] 暴雨红色预警！周边 5 公里内暂无空闲可用骑手。")

    # 返回错误，触发后续 Saga 回滚
    return {"current_error": "COURIER_DISPATCH_TIMEOUT_503"}


# ==============================================================================
# 第四层：逆向补偿节点（Saga Backward Compensator）
# ==============================================================================
def saga_compensator_node(state: SagaOrderState) -> dict:
    """
    【Saga 逆向补偿回滚中心】：
    【核心原理】：后进先出（LIFO）。
    从 compensation_stack 倒序 pop() 出动作，先退款，再退库存，直到栈清空！
    """
    stack = state.get("compensation_stack", []).copy()
    dish = state["dish_name"]
    amount = state["amount"]

    logger.warning("\n" + "=" * 60)
    logger.warning(f"⚠️ 触发 SAGA 分布式回滚！触发根因: {state['current_error']}")
    logger.warning(f"待逆向执行的补偿任务栈总计: {len(stack)} 个")
    logger.warning("=" * 60)

    # 严格按照 LIFO 倒序逐一退还
    while stack:
        action = stack.pop()
        if action == "REFUND_PAYMENT":
            wallet_db["balance"] += amount
            logger.info(f"  [逆向补偿 C2 💸] 执行退款！退还 ${amount:,.2f} 至用户钱包。钱包恢复为: ${wallet_db['balance']:,.2f}")
        elif action == "ROLLBACK_INVENTORY":
            warehouse_db[dish] += 1
            logger.info(f"  [逆向补偿 C1 📦] 释放库存！释放 1 份 {dish} 归还仓储。库存恢复为: {warehouse_db[dish]}")

    logger.warning("✅ SAGA 逆向补偿全部完毕！系统数据库完全恢复至初始纯净状态，无脏数据泄露！")
    return {
        "compensation_stack": [],
        "order_disposition": "CANCELLED_FULLY_COMPENSATED"
    }


# ==============================================================================
# 第五层：路由决策与图拓扑组装
# ==============================================================================
def route_after_inventory(state: SagaOrderState) -> Literal["deduct_payment", "saga_compensator"]:
    if state.get("current_error"):
        return "saga_compensator"
    return "deduct_payment"


def route_after_payment(state: SagaOrderState) -> Literal["dispatch_courier", "saga_compensator"]:
    if state.get("current_error"):
        return "saga_compensator"
    return "dispatch_courier"


def route_after_courier(state: SagaOrderState) -> Literal["confirm_order", "saga_compensator"]:
    if state.get("current_error"):
        return "saga_compensator"
    return "confirm_order"


def confirm_order_node(state: SagaOrderState) -> dict:
    """【终态确认节点】：全部正向事务成功时的圆满交付。"""
    logger.info("🎉 订单全链路履约成功！")
    return {"order_disposition": "FULFILLED"}


def build_saga_graph():
    builder = StateGraph(SagaOrderState)

    # 注册正向推进节点
    builder.add_node("reserve_inventory", reserve_inventory_node)
    builder.add_node("deduct_payment", deduct_payment_node)
    builder.add_node("dispatch_courier", dispatch_courier_node)
    builder.add_node("confirm_order", confirm_order_node)

    # 注册逆向补偿回滚节点
    builder.add_node("saga_compensator", saga_compensator_node)

    # 编排正向边与条件异常路由
    builder.add_edge(START, "reserve_inventory")
    builder.add_conditional_edges("reserve_inventory", route_after_inventory)
    builder.add_conditional_edges("deduct_payment", route_after_payment)
    builder.add_conditional_edges("dispatch_courier", route_after_courier)

    # 终态收敛到 END
    builder.add_edge("confirm_order", END)
    builder.add_edge("saga_compensator", END)

    return builder.compile(checkpointer=MemorySaver())


# ==============================================================================
# 第六层：执行与零差异数据核验沙盒
# ==============================================================================
if __name__ == "__main__":
    app = build_saga_graph()

    print("\n" + "=" * 65)
    print("🛒 下单前外部数据库初始资产状态:")
    print(f"  • 仓储牛排库存: {warehouse_db['Wellington_Steak']} 份")
    print(f"  • 用户钱包余额: ${wallet_db['balance']:,.2f}")
    print("=" * 65 + "\n")

    # 启动订单流程
    order_payload = {
        "order_id": "ORD-SAGA-991",
        "dish_name": "Wellington_Steak",
        "amount": 68.00,
        "compensation_stack": [],
        "current_error": "",
        "order_disposition": "IN_PROGRESS"
    }

    config = {"configurable": {"thread_id": "SESSION_SAGA_TEST"}}
    final_state = app.invoke(order_payload, config=config)

    print("\n" + "=" * 65)
    print("🏁 工作流终止后的最终审计裁判裁决:")
    print("=" * 65)
    print(f"订单处置结果: {final_state['order_disposition']}")
    print(f"记录的故障根因: {final_state['current_error']}")
    print(f"回滚后最终仓储库存: {warehouse_db['Wellington_Steak']} 份 (预期值: 10)")
    print(f"回滚后最终钱包余额: ${wallet_db['balance']:,.2f} (预期值: $100.00)")

    if warehouse_db['Wellington_Steak'] == 10 and wallet_db['balance'] == 100.00:
        print("\n🎯 审计验证 100% 通过！SAGA 模式成功将所有已执行的前序更新全部原子级回滚！")
    else:
        print("\n❌ 严重生产事故: 数据不一致，发生了脏状态泄露！")
    print("=" * 65)
