from typing import TypedDict, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from loguru import logger


# 1. define a global states
class RefundState(TypedDict):
    order_id:int
    amount:float
    reason: str
    risk_level:str # LOW / HIGH
    manager_approved:bool # if it needs human to interrupt
    final_result:str

# 2. define these nodes  the workflow need
def evaluate_refund_node(state: RefundState)->dict:
    logger.info("[node - 1] evaluate_refund_node start")
    amount = state['amount']
    if amount<=30:
        logger.info(f"the amount {amount} is less than 30, so it's low risk")
        return {"risk_level":"LOW"}
    else:
        logger.info(f"the amount exceed 30，amount:{amount}")
        return {"risk_level":"HIGH"}

def auto_refund_node(state:RefundState)->dict:
    logger.info("[node - 2] auto_refund_node start")
    return {
        "final_result": f"on the way refund for amount: {state['amount']} "
    }

def admin_approval_node(state: RefundState)->dict:
    logger.info("[node - 3] human interrupt start")
    if state.get("manager_approved") is True:
        logger.info("✅ the shop owner has been agreed! go refunding")
        return {"final_result": f"refund success✅（approved）：back {state['amount']}"}
    else:
        logger.info("❌ the shop rejected!")
        return {"final_result": "your refund apply was rejected. sorry"}

# 3. define the conditional Edge:
def my_route(state:RefundState)->Literal["auto_refund","admin_approval"]:
    logger.info("[Edge - 1] decide_refund_branch start")
    if state.get("risk_level") == "LOW":
        return "auto_refund"
    else:
        return "admin_approval"

# 4. build and compile a state graph:
def create_refund_workflow():
    builder = StateGraph(RefundState)

    # 1. register above nodes
    builder.add_node("evaluate", evaluate_refund_node)
    builder.add_node("auto_refund", auto_refund_node)
    builder.add_node("admin_approval", admin_approval_node)

    # 2. generate a painting
    builder.add_edge(START, "evaluate")

    # ‼️
    builder.add_conditional_edges(
        "evaluate",
        my_route,
        {
            "auto_refund": "auto_refund",
            "admin_approval": "admin_approval"
        }
    )
    builder.add_edge("auto_refund", END)
    builder.add_edge("admin_approval",END)

    # 核心：引入内存检查点（MemorySaver）以支持挂起与恢复
    checkpointer = MemorySaver()

    # 核心：使用 interrupt_before 在执行 admin_approval 前强制冻结中断！ ⚠️ ⚠️ ⚠️
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["admin_approval"]
    )

# test
if __name__ == "__main__":
    app_graph = create_refund_workflow()
    # 使用唯一的 thread_id 维持会话上下文 (对标 Java ProcessInstanceId)
    config = {"configurable":{"thread_id":"thread_order_1001"}}
    initial_input = {
        "order_id": "ORD_9999",
        "amount": 120.0,
        "reason": "餐食打翻且严重超时"
    }

    # 1. start the workflow:
    app_graph.invoke(initial_input,config)

    # 查看当前图的停滞状态
    current_snapshot = app_graph.get_state(config)

    logger.info("\n⏸️ 【工作流状态检查】")
    logger.info(f"   当前挂起节点: {current_snapshot.next}")
    logger.info(f"   当前全局状态: {current_snapshot.values}")

    logger.info("\n================ 第二阶段：店长登录后台，执行人工审批 ================")
    # 人工介入：更新状态，注入审批意见                                                                               
    app_graph.update_state(config, {"manager_approved": True})
    logger.info("✅ 店长已审批并点击【同意退款】！注入审批结果...")

    logger.info("\n================ 第三阶段：唤醒挂起的工作流，从断点继续执行 ============")
    # 传入 None 恢复执行                                                                                             
    final_output = app_graph.invoke(None, config)
    logger.info("\n🏁 【最终业务结果】")
    logger.info(final_output)




