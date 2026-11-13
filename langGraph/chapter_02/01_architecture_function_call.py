"""
================================================================================
【LangGraph 阶段二：受控 ReAct 内核】第 1 课：企业级零信任工具调用与状态注入（InjectedState）
================================================================================
【核心学习目标】：
1. 掌握企业级安全架构核心：为什么不能让大语言模型拥有完全自主传参的特权？（防止越权篡改身份）
2. 掌握 `langgraph.prebuilt.InjectedState` 机制：
   - 敏感参数（如 `user_id`、`tenant_id`、`token`）对 LLM 隐藏，不出现在 Tool Schema 中；
   - 在 `ToolNode` 运行时，自动从当前图状态 `state` 中安全提取并注入到工具函数中。
3. 理解 LangGraph 官方预置节点 `ToolNode`：
   - 自动解析 `tool_calls`；
   - 自动并行/串行执行绑定的工具；
   - 自动组装 `ToolMessage` 并利用 `add_messages` 写回图状态。
4. 掌握工具 Schema 审查：使用 `convert_to_openai_tool` 查看最终发送给 LLM 的入参定义。
================================================================================
"""

import os
import sys
from pathlib import Path
from typing import Annotated, TypedDict

# 自动将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.graph import add_messages, StateGraph
from langgraph.prebuilt import InjectedState, ToolNode
from loguru import logger

from graph_utils import print_graph_mermaid


# ==============================================================================
# 第一步：定义零信任安全工具（Zero-Trust Enterprise Tool）
# ==============================================================================
# 【核心安全机制 - InjectedState】：
# 1. order_id: 普通业务参数，暴露给 LLM，大模型从用户对话中提取。
# 2. current_user_id: 极其敏感的身份标识！绝对不能让 LLM 自行决定或填写！
#    使用 `Annotated[str, InjectedState("authenticated_user_id")]` 进行声明后：
#    - 该参数在发给 LLM 的 JSON Schema 中会被【彻底抹除】；
#    - 大模型感知不到这个参数的存在，因此黑客无法通过提示词注入（Prompt Injection）伪造他人 ID；
#    - 当 ToolNode 执行该工具时，会从图状态的 state["authenticated_user_id"] 自动取出真实经过身份认证的值并传给它。
@tool
def query_takeout_order(
    order_id: str,
    current_user_id: Annotated[str, InjectedState("authenticated_user_id")]
) -> str:
    """
    根据订单编号查询认证客户的外卖订单实时配送详情。

    Args:
        order_id: 外卖订单唯一编号，例如 'SKY-8899'
    """
    logger.info(f"🔒 [安全工具执行] 订单号: {order_id} | 状态机底层注入的安全用户ID: {current_user_id}")
    # 模拟真实微服务/数据库查询（强行绑定认证用户身份，防止越权查询他人订单）
    return (
        f"订单 {order_id} 详情: 1份经典芝士披萨, 1瓶冰可乐。"
        f"配送状态: 骑手配送中。归属用户核验通过: {current_user_id}。"
    )


# ==============================================================================
# 第二步：定义智能体主状态（Agent State）
# ==============================================================================
class AgentState(TypedDict):
    # 1. 对话历史消息列表：挂载 add_messages 合并器
    # 任何节点返回 {"messages": [new_msg]} 时，会自动根据 id 去重并追加到列表末尾
    messages: Annotated[list[BaseMessage], add_messages]

    # 2. 当前请求经过网关认证的真实用户身份（只读凭据，用于注入工具）
    authenticated_user_id: str


# ==============================================================================
# 第三步：模型接入与思考决策节点（Agent Decision Node）
# ==============================================================================
def get_deepseek_model():
    """获取底层 DeepSeek 客户端。"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=api_key,
        base_url=base_url,
        temperature=0.0,
    )


def agent_decision_node(state: AgentState) -> dict:
    """
    【决策思考节点】：
    - 将安全工具绑定到大模型上；
    - 传入当前对话历史 messages；
    - 模型根据用户指令生成带有 tool_calls 的 AIMessage。
    """
    model = get_deepseek_model()
    # 绑定工具（Tool Calling 协议）
    model_with_tools = model.bind_tools([query_takeout_order])
    
    logger.info("🧠 [Agent Node] 大脑正在分析用户意图...")
    response = model_with_tools.invoke(state["messages"])
    logger.info(f"🧠 [Agent Node] 模型生成决策响应: {response}")

    # 将返回的 AIMessage 包裹在增量字典中返回，由 add_messages 自动追加
    return {"messages": [response]}


# ==============================================================================
# 第四步：构建安全工具执行图
# ==============================================================================
def build_secure_tool_graph():
    builder = StateGraph(AgentState)

    # 1. 注册核心节点：
    builder.add_node("agent", agent_decision_node)
    
    # 2. 【核心预置组件 ToolNode】：
    # 传入工具列表，ToolNode 会全自动完成：
    # - 提取 messages[-1].tool_calls
    # - 解析 InjectedState 参数并从 state 中抓取对应值注入
    # - 执行工具并将结果封装为 ToolMessage
    builder.add_node("tools", ToolNode([query_takeout_order]))

    # 3. 编排静态执行边：START -> agent -> tools -> END
    # （注：本课重点在于观察 InjectedState 的注入机制，下节课我们将接入 ReAct 动态条件循环）
    builder.add_edge(START, "agent")
    builder.add_edge("agent", "tools")
    builder.add_edge("tools", END)

    return builder.compile()


# ==============================================================================
# 第五步：验证与深度 Schema 剖析
# ==============================================================================
if __name__ == "__main__":
    # --- 阶段 1：Schema 安全审查（证明 current_user_id 已被成功隐藏） ---
    print("\n" + "=" * 65)
    print("【安全审查】：查看最终通过网络发送给大模型的 JSON Schema 定义：")
    openai_schema = convert_to_openai_tool(query_takeout_order)
    exposed_params = openai_schema["function"]["parameters"]["properties"]
    print(f"大模型能看到的参数列表: {list(exposed_params.keys())}")
    print("【结果确认】：列表里只有 'order_id'，'current_user_id' 被安全拦截隐藏！")
    print("=" * 65)

    # --- 阶段 2：执行端到端安全图 ---
    app = build_secure_tool_graph()

    # 用户输入仅包含订单号，没有任何用户身份信息
    initial_payload: AgentState = {
        "messages": [HumanMessage(content="你好，麻烦帮我查一下外卖订单 SKY-8899 的最新状态。")],
        "authenticated_user_id": "USR-VIP-CHEN-2026"  # 网关层注入的安全凭证
    }

    print("\n========== 开始执行安全工具调用流程 ==========")
    final_state = app.invoke(initial_payload)

    print("\n" + "=" * 65)
    print("========== 最终对话消息时序链条 ==========")
    for idx, msg in enumerate(final_state["messages"]):
        msg_type = msg.__class__.__name__
        print(f"\n[{idx + 1}] 消息类型: {msg_type}")
        if getattr(msg, "tool_calls", None):
            print(f"    模型请求工具调用: {msg.tool_calls}")
        if getattr(msg, "content", None):
            print(f"    内容: {msg.content}")
    print("=" * 65)

    print_graph_mermaid(app, "01_function_call")
