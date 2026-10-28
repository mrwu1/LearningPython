import operator
import time
from typing import TypedDict, Annotated

from langchain_core.caches import InMemoryCache
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.types import CachePolicy


#声明状态

class OverAllState(TypedDict):
    user:str
    invoke_counts:Annotated[int,operator.add]

def node_a(state:OverAllState):

    time.sleep(3)
    return {
        "invoke_counts":1
    }

builder = StateGraph(OverAllState)

builder.add_node(
    "node_a",
    node_a,
    cache_policy=CachePolicy(ttl=120) #缓存两分钟
)

builder.add_edge(START,"node_a")
builder.add_edge("node_a",END)
builder.set_node_defaults(4)
graph = builder.compile(
    cache=InMemoryCache()
)
print(f"运行结果：{graph.invoke({'user':'ming','invoke_counts':0})}")
print("相同输入再次调用图")
print(f"运行结果：{graph.invoke({'user':'ming','invoke_counts':0})}")