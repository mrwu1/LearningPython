import json
from typing import Annotated, TypedDict
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

# =====================================================================
# 1. 定义工具 (使用 LangChain 官方标准的 @tool 装饰器)
# =====================================================================
# 模拟苍穹外卖真实菜品数据
MOCK_DISHES = {
    "辣子鸡": {"price": 48.0, "stock": 10, "status": "在售"},
    "凉拌黄瓜": {"price": 12.0, "stock": 0, "status": "已售罄"},
    "米饭": {"price": 2.0, "stock": 100, "status": "充足"},
}

@tool
def query_dish_info(dish_name: str) -> str:
    """根据菜品名称查询菜品的真实售价与当前库存状态。

    参数:
    - dish_name: 菜品名称，如'辣子鸡'、'凉拌黄瓜'
    """
    print(f"\n⚙️  [ToolNode 自动调度] 正在执行 Python 工具: query_dish_info(dish_name='{dish_name}')...")
    dish = MOCK_DISHES.get(dish_name)
    if not dish:
        return f"未找到名为 '{dish_name}' 的菜品。"
    
    result = {
        "name": dish_name,
        "price": dish["price"],
        "stock": dish["stock"],
        "status": dish["status"]
    }
    print(f"   工具执行完成，返回真实数据: {result}")
    return json.dumps(result, ensure_ascii=False)


# 工具集合列表
TOOLS = [query_dish_info]


# =====================================================================
# 2. 定义带 Reducer 的全局状态 (State)
# =====================================================================
class AgentState(TypedDict):
    """
    【核心知识点：add_messages Reducer】
    Annotated[list, add_messages] 告诉 LangGraph：
    当任何节点产出新消息时，不要覆盖原有列表，而是自动将新消息做追加合并！
    """
    messages: Annotated[list, add_messages]


# =====================================================================
# 3. 定义大模型推理节点 (Agent Node)
# =====================================================================
# 初始化兼容 OpenAI 协议的本地模型客户端 (连接本地 Ollama，注意 macOS 下使用 127.0.0.1)
llm = ChatOpenAI(
    base_url="http://127.0.0.1:11434/v1",
    api_key="ollama",
    model="llama3.2:3b",
    temperature=0.1
)

# 【核心：将工具绑定给模型】(自动把 @tool 的文档注释转为标准 Function Calling Schema)
llm_with_tools = llm.bind_tools(TOOLS)

def agent_node(state: AgentState) -> dict:
    """【Agent 节点】：接收历史上下文，调用大模型做思考与决策"""
    print("\n🧠 [Agent 思考节点] 正在调用大模型生成决策...")
    response = llm_with_tools.invoke(state["messages"])
    # 只需返回新产生的消息，add_messages 会自动追加合并到全局状态中！
    return {"messages": [response]}


# =====================================================================
# 4. 构建工业级标准图拓扑 (The Standard Tool Calling Graph)
# =====================================================================
def build_production_graph():
    builder = StateGraph(AgentState)

    # 1. 注册核心节点
    builder.add_node("agent", agent_node)
    # 【神级组件：ToolNode】将工具列表直接丢给它，自动处理参数解析、工具并发调度与异常捕获！
    builder.add_node("tools", ToolNode(TOOLS))

    # 2. 编排边流转
    # START -> agent
    builder.add_edge(START, "agent")

    # 【核心条件边：tools_condition】
    # 自动根据 agent 的最新输出判断：
    # - 如果模型想调工具 -> 路由给 "tools" 节点；
    # - 如果模型完成了思考 -> 路由给 END 退出！
    builder.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools": "tools",
            "__end__": END
        }
    )

    # 工具执行完毕后，自动把执行结果喂回给 "agent" 节点继续下一轮思考！
    builder.add_edge("tools", "agent")

    # 编译图工作流
    return builder.compile()


if __name__ == "__main__":
    print("=" * 65)
    print("🚀 启动 LangGraph 标准 ToolNode 工作流")
    print("=" * 65)
    
    graph = build_production_graph()

    # 初始化测试输入：System 指令 + 用户问题
    initial_messages = [
        SystemMessage(content="你是专业外卖助手。当用户询问菜品信息时，请务必调用 query_dish_info 工具查询最新数据，并给出清晰友好的回答。"),
        HumanMessage(content="请帮我查一下店里的辣子鸡多少钱一份？还有没有库存？")
    ]

    print("\n👤 [用户提问]: 请帮我查一下店里的辣子鸡多少钱一份？还有没有库存？\n" + "-" * 65)
    
    try:
        # 执行图
        final_state = graph.invoke({"messages": initial_messages})

        print("\n" + "=" * 65)
        print("🎉 [工作流执行完毕] 最终大模型回复：")
        # 取出历史消息列表里的最后一条消息内容
        print(final_state["messages"][-1].content)
        print("=" * 65)
    except Exception as e:
        print("\n❌ 运行异常，请确保本地 Ollama 服务已启动 (ollama serve)。错误信息:", e)
