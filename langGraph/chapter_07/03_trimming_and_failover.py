"""
================================================================================
【LangGraph 阶段七：生产高可用与分布式防御】第 3 课：上下文智能修剪、预算熔断器与多通道灾备降级（Trimming & Failover）
================================================================================
【核心学习目标】：
1. 掌握上下文智能裁剪（Intelligent Context Trimming）：
   - 核心痛点：多轮对话或长时间 ReAct 循环导致消息列表不断膨胀，超出大模型上下文窗口（Context Window Overflow）且产生巨额 Token 账单；
   - 解决方案：使用 `langchain_core.messages.trim_messages`，采用滑动窗口策略（strategy="last"），只保留最近 N 轮对话，并强制保留开头的 `SystemMessage`（include_system=True）确保智能体人设与安全合规规则不丢失！
2. 掌握大模型多通道自动灾备降级（Model Failover with Fallbacks）：
   - 生产环境中任何三方模型提供商都有可能发生网络抖动、限流（429）或服务器崩溃（503）；
   - 使用 `primary_llm.with_fallbacks([backup_llm])` 实现零停机的秒级主备热切换，主力挂掉时备用模型自动接管。
3. 掌握会话轮次预算熔断器（Budget Circuit Breaker）：
   - 设定单会话最大交互步数上限 `MAX_TURN_BUDGET`，防止 Agent 陷入恶性死循环狂刷 API 导致天价账单。
================================================================================
"""

import sys
from pathlib import Path
from typing import TypedDict, Annotated
from dotenv import find_dotenv, load_dotenv
from loguru import logger

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(find_dotenv())

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    trim_messages
)
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph, add_messages


# ==============================================================================
# 第一层：定义携带预算熔断器的状态契约（State Schema）
# ==============================================================================
class GuardedChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # 消息历史列表
    turn_count: int                                      # 当前会话已消耗的交互步数计数器
    circuit_broken: bool                                 # 熔断器是否触发标志
    final_output: str                                    # 交付给用户的最终内容


# 单会话允许消耗的最大步数上限（防止智能体失控死循环）
MAX_TURN_BUDGET = 5


# ==============================================================================
# 第二层：模拟主力大模型与容灾备用通道（Failover Architecture）
# ==============================================================================

def unstable_primary_llm(messages: list[BaseMessage]) -> AIMessage:
    """模拟主力大模型（如 DeepSeek 主集群）发生突发网络抖动或 503 网关过载崩溃。"""
    logger.error("  [主力 LLM: DeepSeek] 💥 503 Service Unavailable: 服务提供商集群过载！")
    raise ConnectionError("HTTP 503 Provider Outage")


def stable_backup_llm(messages: list[BaseMessage]) -> AIMessage:
    """模拟高可用灾备备用模型（如 Azure OpenAI / 自建灾备集群）在主力挂掉时无缝接管。"""
    logger.info("  [备用 LLM: 灾备降级节点] 🛡️ 主力通道异常，灾备引擎已无缝捕获并接管请求！")
    return AIMessage(content="[灾备通道兜底答复] 您的外卖订单已被调度，骑手正按计划路线火速配送中。")


# ==============================================================================
# 【核心机制】：配置 with_fallbacks 实现自动主备故障转移
# ==============================================================================
primary_runnable = RunnableLambda(unstable_primary_llm)
backup_runnable = RunnableLambda(stable_backup_llm)

# 当 primary_runnable 抛出任何网络或服务异常时，底层自动透明调用 backup_runnable！
resilient_cognitive_engine = primary_runnable.with_fallbacks([backup_runnable])


# ==============================================================================
# 第三层：集成上下文裁剪与预算保护的计算节点
# ==============================================================================
def cognitive_agent_node(state: GuardedChatState) -> dict:
    """
    【受三重防护罩保护的认知节点】：
    防护罩 1：预算熔断器（硬顶拦截超频死循环）
    防护罩 2：智能上下文滑动窗口裁剪（锁定 System 提示词）
    防护罩 3：多模型灾备无感平替（with_fallbacks）
    """
    current_turns = state.get("turn_count", 0) + 1
    logger.info(f"[Agent 认知节点] 正在执行第 {current_turns} 轮交互 / 本会话预算上限: {MAX_TURN_BUDGET} 轮")

    # 1. 【防线一：预算熔断器核查】
    if current_turns > MAX_TURN_BUDGET:
        logger.warning(f"  [熔断器 🚨] 超出单会话最大执行预算步数 ({current_turns} > {MAX_TURN_BUDGET})！紧急刹车熔断。")
        return {
            "turn_count": current_turns,
            "circuit_broken": True,
            "final_output": "BUDGET_EXCEEDED_SESSION_FROZEN"
        }

    # 2. 【防线二：上下文智能裁剪 trim_messages】
    # - max_tokens: 保留的最大 token / 消息条数
    # - strategy="last": 保留最新的消息
    # - include_system=True: 【至关重要】绝不删除最开头的系统人设提示词！
    trimmed_history = trim_messages(
        state["messages"],
        max_tokens=4,           # 教学沙盒设为保留最新 4 条；生产环境通常设为 4000 tokens
        token_counter=len,      # 沙盒演示按消息条数计数
        strategy="last",        # 保留尾部最新对话
        include_system=True     # 无论怎么裁剪，绝对保留开头的 SystemMessage！
    )
    logger.info(f"  [上下文修剪器 ✂️] 将膨胀的 {len(state['messages'])} 条历史智能裁剪为精简的 {len(trimmed_history)} 条！")

    # 3. 【防线三：调用具备灾备热备的推理管道】
    ai_response = resilient_cognitive_engine.invoke(trimmed_history)
    
    return {
        "messages": [ai_response],
        "turn_count": current_turns,
        "circuit_broken": False,
        "final_output": ai_response.content
    }


# ==============================================================================
# 第四层：组装图拓扑
# ==============================================================================
def build_guarded_graph():
    builder = StateGraph(GuardedChatState)
    builder.add_node("agent", cognitive_agent_node)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)
    return builder.compile(checkpointer=MemorySaver())


# ==============================================================================
# 第五层：执行与双重防御验证沙盒
# ==============================================================================
if __name__ == "__main__":
    app = build_guarded_graph()

    # --------------------------------------------------------------------------
    # 演练 1：测试上下文修剪与灾备模型自动故障转移
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("🛡️ 【演练 1】：智能上下文裁剪与灾备故障转移演练")
    print("=" * 65)

    # 构造一份长达 6 条的冗长会话历史
    bloated_messages = [
        SystemMessage(content="你是苍穹外卖专属助手，必须严格保护用户隐私数据。"),
        HumanMessage(content="陈旧问题 1: 你好"),
        AIMessage(content="陈旧回复 1: 您好，请问有什么可以帮您？"),
        HumanMessage(content="陈旧问题 2: 我的新人折扣是多少？"),
        AIMessage(content="陈旧回复 2: 新人首单立减 10% 优惠。"),
        HumanMessage(content="当前最新紧急提问: 我的午饭现在配送到哪里了？")
    ]

    config_normal = {"configurable": {"thread_id": "SESSION_HA_01"}}
    res_1 = app.invoke(
        {"messages": bloated_messages, "turn_count": 0, "circuit_broken": False, "final_output": ""},
        config=config_normal
    )

    print("\n演练 1 审查裁判裁决:")
    print(f"  • 最终输出: {res_1['final_output']}")
    print(f"  • 熔断状态: {res_1['circuit_broken']}")
    print("  • 验证确认: 主力模型发生 503 崩溃时，灾备引擎无缝秒级接管，用户无感知！")

    # --------------------------------------------------------------------------
    # 演练 2：测试会话轮次预算熔断器（拦截死循环失控成本）
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("🛡️ 【演练 2】：失控死循环与 Token 预算熔断器演练")
    print("=" * 65)

    # 模拟一个已经消耗了 5 轮交互的边缘会话，再次发起请求
    exhausted_session_input = {
        "messages": [HumanMessage(content="恶性死循环提问...")],
        "turn_count": 5,  # 已经达到了允许的 5 次阈值
        "circuit_broken": False,
        "final_output": ""
    }

    config_breaker = {"configurable": {"thread_id": "SESSION_RUNAWAY_02"}}
    res_2 = app.invoke(exhausted_session_input, config=config_breaker)

    print("\n演练 2 审查裁判裁决:")
    print(f"  • 最终输出: {res_2['final_output']}")
    print(f"  • 熔断器状态: {res_2['circuit_broken']} (成功触发紧急制动，阻止了失控扣费！)")
    print("=" * 65)
