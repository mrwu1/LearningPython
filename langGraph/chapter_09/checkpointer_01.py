from typing import TypedDict

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from graph_utils import print_graph_mermaid
from util.model import get_llm

# 1. **入参校验**：invoke 传参结构不对，直接报错，提前拦截脏输入
class InputState(TypedDict):
    topic:str

# 1. **输出裁剪**：内部中间字段（poem/joke）不对外暴露，对外接口干净，安全
class OutputState(TypedDict):
    final_output:str

class OverAllState(TypedDict):
    topic:str
    poem:str
    joke:str
    final_output:str

model = get_llm()

# 只是告诉 IDE：**这个节点只需要用到 Input 里的字段 topic**，只是给人看的提示，不会裁剪 state。
def node_poem(state:InputState) -> OverAllState:
    topic = state["topic"]
    poem = model.invoke(
        [
            HumanMessage(f"写一首关于{topic}的诗")
        ]
    ).content
    return {
        "poem":poem
    }

# 只是告诉 IDE：**这个节点只需要用到 Input 里的字段 topic**，只是给人看的提示，不会裁剪 state。
def node_joke(state:InputState) -> OverAllState:
    topic = state["topic"]
    joke = model.invoke(
        [
            HumanMessage(f"写一首关于{topic}的笑话")
        ]
    ).content
    return {
        "joke":joke
    }

def node_final_output(state:OverAllState) -> OutputState:
    topic = state["topic"]
    poem = state["poem"]
    final_output = f"关于{topic},\n{poem}"
    return {
        "final_output":final_output
    }

builder = StateGraph(
    state_schema=OverAllState,
    input_schema=InputState,
    output_schema=OutputState
)

builder.add_node("node_poem",node_poem)
builder.add_node("node_joke",node_joke)
builder.add_node("node_final_output",node_final_output)

builder.add_edge(START,"node_poem")
builder.add_edge(START,"node_joke")
builder.add_edge("node_poem","node_final_output")
builder.add_edge("node_joke","node_final_output")
builder.add_edge("node_final_output",END)

checkpointer = InMemorySaver()
config={
    "configurable":{
        "thread_id":"123"
    }
}

graph = builder.compile(checkpointer=checkpointer)

# res = graph.invoke({"topic":"莲花"},config=config)
# print(res)

history_checkpoints = list(graph.get_state_history(config=config))
print(history_checkpoints)

# recover = graph.invoke(None,config=config)
# print(recover)
