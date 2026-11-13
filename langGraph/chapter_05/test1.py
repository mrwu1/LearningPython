from decimal import Decimal
from typing import TypedDict, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.types import interrupt, Checkpointer, Command


# 1.定义state
class OverAllState(TypedDict,total=False):
    refund_amount:Decimal
    reason:str
    refund_status:Literal["success","rejected","pending"]
    approval_status: str  # 审批状态：PENDING_REVIEW / AUTO_APPROVED / APPROVED / REJECTED
    reviewer_notes: str  # 人工审核员填写的审批批注
    payout_status: str  # 财务打款状态：INITIATED / PENDING_REVIEW / PAID_OUT

# 2.定义node
def router_by_amount(state:OverAllState)->Literal["router_node","__end__"]:
    if state.get("refund_amount")>50:
        #进入人工审核
        return "human_node"
    return END

def human_node(state:OverAllState):
    print(f"金额超出50，进入人工审核阶段")
    amount = state["refund_amount"]
    human_decision = interrupt({
        "alert": "退款金额超出限制，请审核这条退款审批",
        "requested_amount": state["refund_amount"],
        "reason": state["reason"]
    })

    #唤醒后，从这里开始执行
    print(f"\n图已被人类审批唤醒！收到管理员最终裁决: {human_decision}")
    return{
        "approval_status": human_decision.get("approval_status","无状态"),
        "reviewer_notes": human_decision.get("notes","无批注"),
        "refund_amount":human_decision.get("approved_amount", amount)
    }


# 3. build a graph
def create_graph(checkpointer: Checkpointer) -> StateGraph:
    builder = StateGraph(OverAllState)
    builder.add_node("human_node",human_node)

    builder.add_conditional_edges(START,router_by_amount,["human_node","__end__"])
    builder.add_edge("human_node",END)
    return builder.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    checkpointer = MemorySaver()
    app = create_graph(checkpointer)
    config = {
        "configurable":{
            "thread_id":"wuyouzhi1",
        }
    }
    res = app.invoke({
        "refund_amount":20,
        "reason":"不好吃"
    },config = config)
    print(res)

#     第二个
    res1 = app.invoke({
        "refund_amount":60,
        "reason":"不要"
    },config = config)
    print(f"res1: {res1}")
    #校验
    snapshot = app.get_state(config)
    print(f"snapshot: {snapshot}")


    # 唤醒
    manager_approval = {
            "approval_status": "APPROVED",
            "approved_amount": 55.0,  # 扣除5元包装费后同意退款75元
            "notes": "核查送餐记录确实超时，同意退款55元"
     }
    res2 = app.invoke(Command(
        resume=manager_approval,
        # update={
        #     "approval_status": "REJECTED",
        # }
    ),config = config)
    print(f"res2: {res2}")
    snapshot1 = app.get_state(config)
    print(f"snapshot1: {snapshot1}")