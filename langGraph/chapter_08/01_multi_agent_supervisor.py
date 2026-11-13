"""
================================================================================
【LangGraph 阶段八：生产级多智能体协同架构】第 1 课：主控智能体（Supervisor Multi-Agent Pattern）
================================================================================
【核心学习目标】：
1. 掌握多智能体协作黄金范式：主管-专家架构（Supervisor Pattern）：
   - 核心思想：单一单体 Agent 承担过多工具容易发生“工具认知过载”与逻辑混乱；
   - 架构解耦：拆分为一个中心调度主管（Supervisor）和多个垂直领域专家（Specialist Workers）；
   - 主管专注于理解用户意图并分发派单，垂直专家专注于特定业务领域深度作答。
2. 掌握结构化路由决策契约（SupervisorRouteDecision - Pydantic V2）：
   - 主管使用 `llm.with_structured_output(SupervisorRouteDecision, method="function_calling")`；
   - 强制模型输出具有强类型保证的目标专家名称（`dish_advisor` / `order_manager` / `FINISH`）与分发理由。
3. 掌握环形闭环监督拓扑（Cyclic Delegation Loop）：
   - `START -> supervisor -> (conditional) -> specialist -> supervisor`；
   - 专家完成任务后将回答返回给主控主管，由主管进行二次质检，决定继续分发还是终结对话（FINISH）。
================================================================================
"""

import os
import sys
from pathlib import Path
from typing import TypedDict, Literal, Annotated

from dotenv import find_dotenv, load_dotenv

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from graph_utils import print_graph_mermaid

load_dotenv(find_dotenv())
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph, add_messages
from loguru import logger
from pydantic import BaseModel, Field


# ==============================================================================
# 第一步：定义多智能体共享状态与路由决策契约
# ==============================================================================

# 多智能体团队共享的全局工作白板
class MultiAgentState(TypedDict):
    # 对话历史，挂载 add_messages 进行全自动合并
    messages: Annotated[list[BaseMessage], add_messages]
    # 下一个等待执行的垂直专家名称（或 "FINISH"）
    next_worker: str


# 主控主管（Supervisor）输出的强契约结构
class SupervisorRouteDecision(BaseModel):
    next_worker: Literal["dish_advisor", "order_manager", "FINISH"] = Field(
        ...,
        description="下一步指派处理用户请求的专家智能体名称，若已解答完毕则为 FINISH。"
    )
    routing_reason: str = Field(..., description="选择该专家的核心业务判断理由。")


def get_llm():
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.0
    )


# ==============================================================================
# 第二步：定义垂直领域专家智能体（Specialist Workers）
# ==============================================================================

def dish_advisor_worker(state: MultiAgentState) -> dict:
    """
    【垂直专家 1：点餐美食品鉴顾问（Dish Advisor）】：
    专门负责：健康减脂、营养卡路里计算、菜系口味推荐。
    """
    llm = get_llm()
    system_prompt = (
        "你是苍穹外卖的美食品鉴高级顾问。\n"
        "你精通各种菜系搭配、减脂控卡与健康膳食指南。\n"
        "请根据顾客的诉求，以专业、热情的语气在2句话内给出最匹配的菜品推荐。"
    )

    response = llm.invoke([SystemMessage(content=system_prompt)] + state["messages"])
    
    # 专家产出带有专属身份标签的回答，并建议下一步走向 FINISH
    return {
        "messages": [AIMessage(content=f"【美食品鉴专家】: {response.content}")],
        "next_worker": "FINISH"
    }


def order_manager_worker(state: MultiAgentState) -> dict:
    """
    【垂直专家 2：订单与履约调度管家（Order Manager）】：
    专门负责：订单实时状态查询、骑手 GPS 追踪、送达耗时预估。
    """
    # 模拟内部物流系统的实时遥测数据
    courier_status = "骑手【小王】已在商家取餐，当前距您 1.2 公里，预计 7 分钟内送达。"

    system_prompt = (
        f"你是苍穹外卖的订单与履约管理专家。当前实时物流遥测数据为: '{courier_status}'。\n"
        "请礼貌安抚顾客，并在2句话内清晰告知当前送餐进度与预计时间。"
    )
    llm = get_llm()
    response = llm.invoke([SystemMessage(content=system_prompt)] + state["messages"])

    return {
        "messages": [AIMessage(content=f"【履约调度专家】: {response.content}")],
        "next_worker": "FINISH"
    }


# ==============================================================================
# 第三步：定义主控调度主管节点（Supervisor Brain）
# ==============================================================================
def supervisor_node(state: MultiAgentState) -> dict:
    """
    【中央总控大脑（Supervisor）】：
    不直接做业务繁重的细节答复，而是充当调度中枢：
    通过结构化输出（Structured Output via Function Calling）精准将任务派发给最胜任的专家。
    """
    supervisor_system_prompt = (
        "你是苍穹外卖多智能体协作系统的中央总控调度官（Supervisor）。\n"
        "你的唯一职责是审查对话，并将任务指派给最合适的垂直领域专家：\n"
        "  1. 'dish_advisor' : 负责菜品推荐、热量卡路里、营养搭配、口味喜好。\n"
        "  2. 'order_manager': 负责订单状态、送达时间、骑手定位、配送催单。\n"
        "  3. 'FINISH'       : 如果用户的问题此前已经被专家圆满回答，无需进一步派发。"
    )
    llm = get_llm()
    # 采用工具调用模式（Function Calling）强制输出符合 SupervisorRouteDecision 模型的结构体
    structured_llm = llm.with_structured_output(SupervisorRouteDecision, method="function_calling")
    
    whole_messages = [SystemMessage(content=supervisor_system_prompt)] + state["messages"]
    logger.info("🧠 [Supervisor] 正在审视全局历史，进行专家派发决策...")
    decision: SupervisorRouteDecision = structured_llm.invoke(whole_messages)

    logger.info(f"🎯 [Supervisor] 派发指令 -> '{decision.next_worker}' | 决策依据: {decision.routing_reason}")
    return {"next_worker": decision.next_worker}


# ==============================================================================
# 第四步：定义条件路由分发函数
# ==============================================================================
def route_from_supervisor(state: MultiAgentState) -> Literal["dish_advisor", "order_manager", END]:
    """根据主管写入 state 的 next_worker，动态跳往对应的专家节点或直接结束。"""
    target = state.get("next_worker", "FINISH")
    if target == "FINISH" or not target:
        return END
    return target


# ==============================================================================
# 第五步：组装多智能体团队拓扑
# ==============================================================================
def build_supervisor_graph():
    builder = StateGraph(MultiAgentState)

    # 1. 注册核心节点
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("dish_advisor", dish_advisor_worker)
    builder.add_node("order_manager", order_manager_worker)

    # 2. 初始入口指向主管
    builder.add_edge(START, "supervisor")

    # 3. 主管向垂直专家或 END 条件分流
    builder.add_conditional_edges("supervisor", route_from_supervisor)

    # 4. 【环形反馈闭环】：所有专家完成后，重新返回 supervisor 节点进行结果验收！
    builder.add_edge("dish_advisor", "supervisor")
    builder.add_edge("order_manager", "supervisor")

    return builder.compile(checkpointer=MemorySaver())


# ==============================================================================
# 第六步：双场景实战执行验证
# ==============================================================================
if __name__ == "__main__":
    app = build_supervisor_graph()
    print_graph_mermaid(app, "01_supervisor_multi_agent")

    # --------------------------------------------------------------------------
    # 场景 1：点餐诉求（预期由 supervisor 派发给 dish_advisor）
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("【场景 1】：健康低卡点餐诉求...")
    scenario_1_input = {
        "messages": [HumanMessage(content="我想吃一份健康低卡的晚餐，最好有三文鱼，热量在 500 大卡以内。")],
        "next_worker": ""
    }
    cfg_1 = {"configurable": {"thread_id": "SESSION_MULTI_01"}}
    res_1 = app.invoke(scenario_1_input, config=cfg_1)
    print("\n最终对话产出:\n" + res_1["messages"][-1].content)

    # --------------------------------------------------------------------------
    # 场景 2：催单诉求（预期由 supervisor 派发给 order_manager）
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("【场景 2】：暴雨送餐催单诉求...")
    scenario_2_input = {
        "messages": [HumanMessage(content="我的午饭现在送到哪了？外面在下大雨，骑手是不是迷路了？")],
        "next_worker": ""
    }
    cfg_2 = {"configurable": {"thread_id": "SESSION_MULTI_02"}}
    res_2 = app.invoke(scenario_2_input, config=cfg_2)
    print("\n最终对话产出:\n" + res_2["messages"][-1].content)
    print("=" * 65)
