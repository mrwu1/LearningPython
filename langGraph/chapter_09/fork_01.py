import sys
from pathlib import Path
from typing import TypedDict, Annotated, Literal

# 将项目根目录加入 sys.path，保证在任意目录下执行脚本都能正确导入 graph_utils 和 util
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from graph_utils import print_graph_mermaid
from util.model import get_llm


# 【复盘错误 1】原状态缺少 topic 和 mode 字段：
# router_node 提取出的结构化结果需要写回全局 State；如果全局 State 没声明这两个字段，
# LangGraph 不会持久化它们，导致后续 node_poem/node_joke 读取 state["topic"] 时抛出 KeyError。
# 这里加上 total=False 允许部分字段初始为空。
class OverAllState(TypedDict, total=False):
    username: str
    user_input: str
    topic: str
    mode: Literal["poem", "joke"]
    output: str


# add it to llm
class StructedOutputState(TypedDict):
    topic: Annotated[str, "主题"]
    mode: Annotated[Literal["poem", "joke"], "模式"]


model = get_llm()
# 【复盘错误 6】DeepSeek 等第三方兼容 OpenAI 接口的模型不支持 response_format: {"type": "json_schema"}：
# 默认情况下 with_structured_output 会尝试使用 json_schema 模式，导致 DeepSeek 报:
# "This response_format type is unavailable now (invalid_request_error)"。
# 必须显式指定 method="function_calling" 使用工具调用 (Tool Call) 来输出结构化数据。
model_with_structure = model.with_structured_output(schema=StructedOutputState, method="function_calling")


def router_node(state: OverAllState) -> StructedOutputState:
    user_input = state["user_input"]
    res = model_with_structure.invoke([
        HumanMessage(user_input)
    ])
    return res


# 【复盘错误 2】字典索引错误：
# 原写法是 `return state["node_poem"]`，state 字典中根本没有 "node_poem" 这个键，会直接报 KeyError。
# 条件边路由函数应该直接返回目标节点的名称字符串（例如 "node_poem"、"node_joke"）。
def router(state: OverAllState) -> Literal["node_poem", "node_joke", "node_default"]:
    if state.get("mode") == "poem":
        return "node_poem"
    elif state.get("mode") == "joke":
        return "node_joke"
    return "node_default"


def node_poem(state: OverAllState) -> OverAllState:
    topic = state.get("topic", "")
    poem = model.invoke([
        HumanMessage(f"写一首关于{topic}的七言绝句")
    ]).content
    return {
        "output": poem
    }


def node_joke(state: OverAllState) -> OverAllState:
    topic = state.get("topic", "")
    joke = model.invoke([
        HumanMessage(f"写关于{topic}的笑话")
    ]).content
    return {
        "output": joke
    }


def node_default(state: OverAllState) -> OverAllState:
    return {
        "output": "无法处理的类型"
    }


builder = StateGraph(state_schema=OverAllState)
builder.add_node("node_poem", node_poem)
builder.add_node("node_joke", node_joke)
builder.add_node("node_default", node_default)

# 【复盘错误 3】把 add_node 误写成了 add_edge：
# 原写法是 `builder.add_edge("router_node", router_node)`，不仅第二个参数误传了函数对象，
# 而且 router_node 节点根本没有被添加到图中，导致后续 builder.add_edge(START, "router_node") 报节点不存在。
builder.add_node("router_node", router_node)

builder.add_edge(START, "router_node")
builder.add_conditional_edges("router_node", router, path_map=["node_poem", "node_joke", "node_default"])
builder.add_edge("node_poem", END)
builder.add_edge("node_joke", END)
builder.add_edge("node_default", END)

checkpointer = InMemorySaver()

config = {
    "configurable": {
        "thread_id": "456789"
    }
}
graph = builder.compile(checkpointer=checkpointer)
print_graph_mermaid(graph, "fork")

# 【复盘错误 4 & 5】入参 key 不匹配 & 缺少 config：
# 1) 原入参是 {"topic": "月亮"}，但 router_node 取的是 state["user_input"]，会报 KeyError: 'user_input'。
# 2) 图编译时挂载了 checkpointer=InMemorySaver()，此时 invoke 必须传入包含 thread_id 的 config，否则报 Checkpointer 缺失错误。
res = graph.invoke({
    "user_input": "请帮我写一首关于月亮的七言绝句"
}, config=config)

print(res)
