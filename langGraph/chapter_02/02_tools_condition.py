"""
================================================================================
【LangGraph 阶段二：受控 ReAct 内核】第 2 课：生产级 ReAct 引擎与 tools_condition 条件路由
================================================================================
【核心学习目标】：
1. 掌握工厂模式（Factory Pattern）管理大模型与推理节点，避免高频创建对象。
2. 掌握官方内置路由组件 `langgraph.prebuilt.tools_condition`：
   - 自动检测上一条消息是否有 `tool_calls`；
   - 有则路由到名为 `"tools"` 的节点；无则路由到 `END`。
3. 掌握经典 ReAct 闭环编排：
   - `START -> agent -> (tools_condition) -> tools -> agent`
4. 区分“确定性单向图”与“自省循环图”的本质区别。
================================================================================
"""

import os
import sys
from pathlib import Path
from typing import TypedDict, Annotated, Callable

# 自动向上递归寻找 .env，彻底解决找不到 API Key 的环境问题
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

# 将项目根目录加进 sys.path，保证 graph_utils 无论在任何终端路径下都能成功 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.constants import START
from langgraph.graph import add_messages, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from loguru import logger

from graph_utils import print_graph_mermaid


# ==============================================================================
# 第一层：基础设施层（模型单例工厂 Model Factory）
# ==============================================================================
# 【设计心法】：
# 在高并发微服务或多步循环中，避免在每个节点内部重复实例化 ChatOpenAI。
# 通过类方法维护全局单例连接池，减少握手开销。
class LLMClientFactory:
    """企业级模型工厂：负责管理 LLM 生命周期与单例连接。"""
    _model_instance: ChatOpenAI | None = None

    @classmethod
    def get_chat_model(cls) -> ChatOpenAI:
        if cls._model_instance is None:
            api_key = os.getenv("DEEPSEEK_API_KEY")
            base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            cls._model_instance = ChatOpenAI(
                model="deepseek-chat",
                api_key=api_key,
                base_url=base_url,
                temperature=0.0  # 智能体任务通常使用 0.0 温度，保证输出确定性与工具调用的精准度
            )
        return cls._model_instance


# ==============================================================================
# 第二层：领域状态（State）与业务工具（Tools）
# ==============================================================================

@tool
def get_chef_specials(cuisine_category: str) -> str:
    """
    根据给定的菜系类别（如 'Italian' 意餐，'Sichuan' 川菜）查询主厨招牌推荐菜品。

    Args:
        cuisine_category: 菜系名称，例如 'Italian'、'Sichuan' 等
    """
    logger.info(f"🔧 [执行工具 get_chef_specials] 传入菜系参数: {cuisine_category}")
    cuisine_lower = cuisine_category.lower()
    if "italian" in cuisine_lower:
        return "1. 黑松露意面 ($28), 2. 窑烤玛格丽特披萨 ($18)。"
    elif "sichuan" in cuisine_lower:
        return "1. 传统麻婆豆腐 ($14), 2. 经典宫保鸡丁 ($16)。"
    return "主厨特选品鉴套餐 ($45)。"


# 【智能体主状态】：
# 仅包含 messages 通道，挂载 add_messages 进行状态叠加
class ReActAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# ==============================================================================
# 第三层：高阶节点工厂（Pure Business Node Factory）
# ==============================================================================
# 【闭包与依赖注入】：
# 通过工厂函数将已经绑定好工具的 model 注入到节点闭包中，
# 保持节点本身满足 `state -> dict` 的纯函数签名规范。
def create_reasoning_node(model: Runnable) -> Callable[[ReActAgentState], dict]:
    """创建并注入已绑定工具模型的推理节点函数。"""
    def agent_node(state: ReActAgentState) -> dict:
        logger.info("\n🧠 [Agent 思考节点] 正在分析当前完整对话历史...")
        response = model.invoke(state["messages"])
        logger.info(f"🧠 [Agent 思考节点] 模型产出内容: {response}")
        # 返回 AIMessage，由 add_messages 自动更新到 messages 列表中
        return {"messages": [response]}
    return agent_node


# ==============================================================================
# 第四层：图拓扑编排（生产级经典 ReAct 闭环）
# ==============================================================================
def build_react_agent_graph() -> Runnable:
    # 1. 准备工具列表并完成与底层大模型的预绑定
    tools = [get_chef_specials]
    base_llm = LLMClientFactory.get_chat_model()
    model_with_tools = base_llm.bind_tools(tools)

    # 2. 初始化状态图构建器
    builder = StateGraph(ReActAgentState)

    # 3. 注册节点：
    # - "agent": 负责思考和决定是否调用工具
    builder.add_node("agent", create_reasoning_node(model_with_tools))
    # - "tools": 负责执行工具。
    # 【注意】：节点名称必须严格命名为 "tools"，因为官方的 tools_condition 默认寻找的就是名为 "tools" 的节点！
    builder.add_node("tools", ToolNode(tools))

    # 4. 起点连接到思考节点
    builder.add_edge(START, "agent")

    # 5. 【核心 API：tools_condition 条件路由】
    # 工作逻辑：
    # - 如果上一条消息有 tool_calls -> 转向 "tools" 节点；
    # - 如果上一条消息没有 tool_calls -> 转向 END 结束。
    builder.add_conditional_edges(
        source="agent",
        path=tools_condition
    )

    # 6. 【ReAct 循环边】：
    # 工具节点执行完毕产出 ToolMessage 后，无条件重新流向 agent 节点让大模型进行综合总结！
    builder.add_edge("tools", "agent")

    # 7. 编译生成运行时可执行对象
    return builder.compile()


# ==============================================================================
# 第五步：测试与执行验证
# ==============================================================================
if __name__ == "__main__":
    app = build_react_agent_graph()
    print_graph_mermaid(app, "02_react_loop")

    initial_payload: ReActAgentState = {
        "messages": [HumanMessage(content="你好，今晚想吃意大利菜，有什么推荐的主厨招牌菜吗？")]
    }

    print("\n========== 开始执行生产级 ReAct 循环 ==========")
    final_state = app.invoke(initial_payload)

    print("\n" + "=" * 65)
    print("========== 最终对话时序记录 ==========")
    for idx, msg in enumerate(final_state["messages"]):
        print(f"\n[轮次 {idx + 1}] 角色: {msg.__class__.__name__}")
        if getattr(msg, "tool_calls", None):
            print(f"  * 请求调用工具: {msg.tool_calls}")
        if getattr(msg, "content", None):
            print(f"  * 文本内容:\n{msg.content}")
    print("=" * 65)
