import time
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import interrupt, Command


class OverAllState(TypedDict):
    username: str
    age: int

def node_a(state:OverAllState)->OverAllState:
    username = interrupt("请输入您的姓名")
    return {
        "username": username
    }
def node_b(state:OverAllState)->OverAllState:
    age = interrupt("请输入您的年龄")
    return {
        "age": age
    }

builder = StateGraph(state_schema= OverAllState)
builder.add_node("node_a", node_a)
builder.add_node("node_b", node_b)

builder.add_edge(START, "node_a")
builder.add_edge("node_a", "node_b")
builder.add_edge("node_b", END)

checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)

# 执行，触发中断
config = {"configurable":{"thread_id":"999"}}
interrupt_res = graph.invoke({},config=config)
print(interrupt_res)

#恢复执行

resume_map ={}

for i in interrupt_res["__interrupt__"]:
    user_input = input(f"{i.value}:")
    if "年龄" in i.value:
        resume_map[i.id] = int(user_input)
    else:
        resume_map[i.id] = user_input

resume_res = graph.invoke(Command(resume = resume_map),config=config)
print(resume_res)

for i in resume_res["__interrupt__"]:
    user_input = input(f"{i.value}:")
    if "年龄" in i.value:
        resume_map[i.id] = int(user_input)
    else:
        resume_map[i.id] = user_input

resume_res1 = graph.invoke(Command(resume = resume_map),config=config)
print(resume_res1)