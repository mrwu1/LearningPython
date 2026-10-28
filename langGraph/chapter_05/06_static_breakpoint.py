from typing import Annotated, TypedDict
import operator
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

class ApprovalState(TypedDict):
    task: str
    approved: bool
    log: Annotated[list[str], operator.add]

def propose(state: ApprovalState) -> dict:
    return {"log": [f"Proposed task: {state['task']}"]}

def execute(state: ApprovalState) -> dict:
    if state["approved"]:
        return {"log": [f"Executing: {state['task']}"]}
    return {"log": ["Task rejected."]}

builder = StateGraph(ApprovalState)
builder.add_node("propose", propose)
builder.add_node("execute", execute)
builder.add_edge(START, "propose")
builder.add_edge("propose", "execute")
builder.add_edge("execute", END)

memory = MemorySaver()
# 关键：在 execute 节点执行前暂停
graph = builder.compile(
    checkpointer=memory,
    interrupt_before=["execute"]
)

config = {"configurable": {"thread_id": "approval-1"}}

# 第一次运行，会在 propose 之后、execute 之前暂停
result = graph.invoke(
    {"task": "Deploy to production", "approved": False, "log": []},
    config
)
print("暂停时的 log:", result["log"])
# 输出: ['Proposed task: Deploy to production']
print(result)

# 人工审批：修改状态，把 approved 设为 True
# graph.update_state(config, {"approved": True})
# 恢复执行，传入 None 从检查点继续
# final = graph.invoke(None, config)
# print("最终 log:", final["log"])
# 输出: ['Proposed task: Deploy to production', 'Executing: Deploy to production']