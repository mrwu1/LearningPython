from typing import Literal

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.constants import END, START
from langgraph.graph import MessagesState, StateGraph

from util.model import get_llm


@tool(parse_docstring=True)
def get_weather(city: str) -> str:
    """
    查询指定城市当日的天气

    Args:
         city:城市名称
    """
    return f"{city}天气晴朗，微风"


@tool(parse_docstring=True)
def get_news(home_or_abroad: bool) -> str:
    """
    查询国内外的新闻

    Args:
         home_or_abroad: 查询国内或者国外的新闻 True:国内新闻，False:国外新闻
    """
    return "新疆棉花" if home_or_abroad else "新西兰景点"


model = get_llm()
tools = [get_weather, get_news]
tools_by_name = {t.name: t for t in tools}
llm_with_tools = model.bind_tools(tools)   # 注意拼写


class OverState(MessagesState):
    user_input: str
    output: str


def llm_node(state: OverState) -> OverState:
    # 直接用 state["messages"]，不要依赖 user_input
    res = llm_with_tools.invoke(state["messages"])
    return {"messages": [res]}

# 核心：✅✅✅
def tool_node(state: OverState) -> OverState:
    # 根据llm的输出消息，获取需要调用的工具集合
    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool_fn = tools_by_name[tool_call["name"]]
        observation = tool_fn.invoke(tool_call["args"]) # ✅✅✅
        result.append(
            ToolMessage(content=str(observation), tool_call_id=tool_call["id"])
        )
    return {"messages": result}


def router(state: OverState) -> Literal["tool_node", END]:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tool_node"
    return END


builder = StateGraph(state_schema=OverState)
builder.add_node("llm_node", llm_node)
builder.add_node("tool_node", tool_node)

builder.add_edge(START, "llm_node")
builder.add_conditional_edges("llm_node", router, path_map=["tool_node", END])
builder.add_edge("tool_node", "llm_node")

graph = builder.compile()

res = graph.invoke(
    {"messages": [HumanMessage(content="今天杭州的天气怎么样？国内有什么新闻？")]}
)
for msg in res["messages"]:
    msg.pretty_print()