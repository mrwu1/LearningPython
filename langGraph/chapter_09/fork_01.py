from typing import TypedDict, Annotated, Literal

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from graph_utils import print_graph_mermaid
from util.model import get_llm


class OverAllState(TypedDict):
    username: str
    user_input: str
    output: str

# add it to llm
class StructedOutputState(TypedDict):
    topic:Annotated[str,"主题"]
    mode:Annotated[Literal["poem","joke"],"模式"]

model = get_llm()
model_with_structure= model.with_structured_output(schema=StructedOutputState)

def router_node(state: OverAllState)->StructedOutputState:
    user_input = state["user_input"]
    res = model_with_structure.invoke([
        HumanMessage(user_input)
    ])
    return res

def router(state:StructedOutputState)->Literal["node_poem","node_joke","node_default"]:
    if state["mode"] == "poem":
        return state["node_poem"]
    elif state["mode"] == "joke":
        return state["node_joke"]
    return "node_default"

def node_poem(state:StructedOutputState)->OverAllState:
    topic = state["topic"]
    poem = model.invoke([
        HumanMessage(f"写一首关于{topic}的七言绝句")
    ]).content
    return {
        "output": poem
    }
def node_joke(state:StructedOutputState)->OverAllState:
    topic = state["topic"]
    joke = model.invoke([
        HumanMessage(f"写关于{topic}的笑话")
    ]).content
    return {
        "output": joke
    }
def node_default(state:StructedOutputState)->OverAllState:
    return {
        "output":"无法处理的类型"
    }

builder = StateGraph(state_schema=OverAllState)
builder.add_node("node_poem",node_poem)
builder.add_node("node_joke",node_joke)
builder.add_node("node_default",node_default)
builder.add_edge("router_node",router_node)

builder.add_edge(START,"router_node")
builder.add_conditional_edges("router_node",router,path_map=["node_poem","node_joke","node_default"])
builder.add_edge("node_poem",END)
builder.add_edge("node_joke",END)
builder.add_edge("node_default",END)

checkpointer = InMemorySaver()

config = {
    "configurable":{
        "thread_id":'456789'
    }
}
graph = builder.compile(checkpointer=checkpointer)
print_graph_mermaid(graph,"fork")

res = graph.invoke({
    "topic":"月亮"
})
print(res)