"""
================================================================================
【LangGraph 阶段二：受控 ReAct 内核】第 2 课：手动实现 Tool 决策与执行闭环（原生 ReAct Loop）
================================================================================
【核心学习目标】：
1. 掌握 `@tool(parse_docstring=True)`：如何将 Python 函数声明为 LLM 可识别的标准工具。
2. 掌握 `MessagesState`：LangGraph 预置的标准消息状态容器（内置 add_messages 合并器）。
3. 掌握大模型工具绑定：`model.bind_tools(tools)` 是如何赋予模型输出 `tool_calls` 能力的。
4. 深度剖析 ToolNode 内部机制：手动编写工具执行节点，理解 `ToolMessage` 与 `tool_call_id` 的配对原理。
5. 掌握 ReAct 循环流转：LLM 决策 -> 是否调用工具 -> 执行工具生成 ToolMessage -> 反哺 LLM 生成最终回答。
================================================================================
"""

import sys
from pathlib import Path
from typing import Literal

# 自动将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.constants import END, START
from langgraph.graph import MessagesState, StateGraph

from graph_utils import print_graph_mermaid
from util.model import get_llm


# ==============================================================================
# 第一步：定义领域业务工具（Domain Business Tools）
# ==============================================================================
# 【@tool 核心要点】：
# 1. 函数文档字符串（Docstring）是大模型的“使用说明书”！LLM 就是通过读文档来决定什么时候调用它。
# 2. 参数类型注解（type annotations）会被自动转换为 JSON Schema，限制模型生成的入参类型。
# 3. parse_docstring=True 表示启用高级文档解析，提取 Args 里的参数说明。

@tool(parse_docstring=True)
def get_weather(city: str) -> str:
    """
    查询指定城市当日的天气情况。

    Args:
         city: 目标城市名称，例如 '杭州'、'北京'
    """
    return f"{city}天气晴朗，气温 22℃，微风"


@tool(parse_docstring=True)
def get_news(home_or_abroad: bool) -> str:
    """
    查询最新的国内外重要新闻头条。

    Args:
         home_or_abroad: 查询国内还是国外的新闻。True 代表国内新闻，False 代表国外新闻。
    """
    return "【国内要闻】：科技创新成果显著，新能源汽车出口再创新高！" if home_or_abroad else "【国际要闻】：联合国环境大会召开，达成多项绿色共识。"


# ==============================================================================
# 第二步：模型与工具准备
# ==============================================================================
# 1. 获取底层模型
model = get_llm()

# 2. 组装工具清单
tools = [get_weather, get_news]

# 3. 建立工具名称到函数对象的快速查找映射字典（供后续手工执行节点使用）
tools_by_name = {t.name: t for t in tools}

# 4. 【核心 API】：bind_tools
# 将工具转换成 OpenAI Function Calling 规范并绑定到模型上。
# 绑定后，LLM 若判定需要查询外部数据，输出的 AIMessage 中就会包含 tool_calls 结构！
llm_with_tools = model.bind_tools(tools)


# ==============================================================================
# 第三步：定义全局状态（继承 MessagesState）
# ==============================================================================
# 【MessagesState 是什么？】：
# LangGraph 提供的一个标准基础 TypedDict，它的源码等价于：
# class MessagesState(TypedDict):
#     messages: Annotated[list[BaseMessage], add_messages]
# 这里继承 MessagesState，就自动拥有了 messages 通道以及 add_messages 去重追加能力！
class OverState(MessagesState):
    user_input: str  # 可扩展的额外业务字段
    output: str      # 最终总结字段


# ==============================================================================
# 第四步：定义核心节点（Node）与条件路由（Router）
# ==============================================================================

def llm_node(state: OverState) -> dict:
    """
    【LLM 推理节点（大脑思考）】：
    - 将整个历史会话 messages 传递给绑定了工具的模型；
    - 模型根据上下文做出判断：
      * 如果需要工具，返回带有 tool_calls 的 AIMessage；
      * 如果信息充分，返回直接回答给用户的文本 AIMessage。
    """
    print("\n---> [Node: llm_node] 大脑开始推理上下文...")
    res = llm_with_tools.invoke(state["messages"])
    # 返回列表，触发 add_messages 合并器自动追加到对话历史中
    return {"messages": [res]}


def tool_node(state: OverState) -> dict:
    """
    【手动工具执行节点（手臂行动）】：
    【核心机制剖析】：这就是 LangGraph 官方 ToolNode 底层的真实运作原理！
    1. 拿到上一轮 LLM 输出的 AIMessage；
    2. 读取其中的 tool_calls 列表（支持多个工具并发调用）；
    3. 根据 tool_call["name"] 找到对应的 Python 函数；
    4. 将 tool_call["args"] 参数传入并执行函数；
    5. 【至关重要】：将执行结果封装成 ToolMessage，并且必须附带 tool_call_id！
       （大模型通过 tool_call_id 将工具返回的结果与它当时发起的调用一一对应）。
    """
    print("\n---> [Node: tool_node] 正在执行外部工具调用...")
    last_message = state["messages"][-1]
    result_messages = []

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        call_id = tool_call["id"]
        
        print(f"  * 调度工具: [{tool_name}] | 参数: {tool_args} | 编号: {call_id}")
        tool_fn = tools_by_name[tool_name]
        
        # 真正执行 Python 工具函数
        observation = tool_fn.invoke(tool_args)
        
        # 封装为 LangChain 标准 ToolMessage
        result_messages.append(
            ToolMessage(
                content=str(observation),
                tool_call_id=call_id
            )
        )

    return {"messages": result_messages}


def router(state: OverState) -> Literal["tool_node", END]:
    """
    【ReAct 路由分流器】：
    - 检查最后一条消息是否包含 tool_calls：
      * 若包含：说明模型请求外部工具辅助，跳转到 "tool_node"；
      * 若不包含：说明模型已经得出最终答案，流程流向 END 结束。
    """
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        print("=== [Router] 检测到模型生成了工具调用意图 -> 路由到 [tool_node]")
        return "tool_node"
    
    print("=== [Router] 模型完成最终作答，无需再调用工具 -> 路由到 [END]")
    return END


# ==============================================================================
# 第五步：组装图拓扑（构建经典的 ReAct 闭环）
# ==============================================================================
builder = StateGraph(state_schema=OverState)

# 1. 添加节点
builder.add_node("llm_node", llm_node)
builder.add_node("tool_node", tool_node)

# 2. 初始入口连向思考节点
builder.add_edge(START, "llm_node")

# 3. 思考后的动态条件分流：指向 tool_node 或直接收敛到 END
builder.add_conditional_edges(
    "llm_node",
    router,
    path_map=["tool_node", END]
)

# 4. 【闭环核心】：工具执行完成后，必须重新把结果喂回 llm_node 再次思考！
builder.add_edge("tool_node", "llm_node")

# 5. 编译图
graph = builder.compile()


# ==============================================================================
# 第六步：执行与验证
# ==============================================================================
if __name__ == "__main__":
    print_graph_mermaid(graph, "tool_hand")

    print("\n========== 开始执行手工 ReAct 智能体 ==========")
    # 提问中同时包含了天气和新闻两个维度的需求，验证 LLM 的多工具并行调用能力
    res = graph.invoke(
        {"messages": [HumanMessage(content="今天杭州的天气怎么样？国内有什么新闻？")]}
    )

    print("\n" + "=" * 65)
    print("========== 最终对话完整时序历史（Pretty Print） ==========")
    print("=" * 65)
    for msg in res["messages"]:
        msg.pretty_print()
