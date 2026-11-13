from typing import TypedDict, List, Literal

from langchain_core.messages import BaseMessage, SystemMessage, AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.types import Checkpointer
from langgraph_runtime_inmem.checkpoint import InMemorySaver
from loguru import logger
from pydantic import BaseModel, Field

from graph_utils import print_graph_mermaid
from util.model import get_llm


class OverAllState(TypedDict):
    messages:List[BaseMessage]
    next_worker:str

llm = get_llm()
def dish_advisor_node(state: OverAllState)->dict:
    """
        【垂直专家 1：点餐美食品鉴顾问（Dish Advisor）】：
        专门负责：健康减脂、营养卡路里计算、菜系口味推荐。
    """
    system_prompt = (
        "你是苍穹外卖的美食品鉴高级顾问。\n"
        "你精通各种菜系搭配、减脂控卡与健康膳食指南。\n"
        "请根据顾客的诉求，以专业、热情的语气在2句话内给出最匹配的菜品推荐。"
    )
    whole_messages = [SystemMessage(content=system_prompt)]+state["messages"]
    res = llm.invoke(whole_messages)
    logger.info(f"点菜经理完成模型访问：{res}")
    return{
        "messages": [AIMessage(content=res.content)],
        "next_worker": "FINISH"
    }

def order_manager_node(state: OverAllState)->dict:
    #订单经理
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
    logger.info(f"订单经理完成模型访问：{response}")

    return {
        "messages": [AIMessage(content=f"【履约调度专家】: {response.content}")],
        "next_worker": "FINISH"
    }

# 主控主管（Supervisor）输出的强契约结构
class SupervisorRouteDecision(BaseModel):
    next_worker: Literal["dish_advisor", "order_manager", "FINISH"] = Field(
        ...,
        description="下一步指派处理用户请求的专家智能体名称，若已解答完毕则为 FINISH。"
    )
    routing_reason: str = Field(..., description="选择该专家的核心业务判断理由。")

def supervisor_node(state: OverAllState)->dict:
    #大脑，负责分配任务
    supervisor_system_prompt = (
        "你是苍穹外卖多智能体协作系统的中央总控调度官（Supervisor）。\n"
        "你的唯一职责是审查对话，并将任务指派给最合适的垂直领域专家：\n"
        "  1. 'dish_advisor' : 负责菜品推荐、热量卡路里、营养搭配、口味喜好。\n"
        "  2. 'order_manager': 负责订单状态、送达时间、骑手定位、配送催单。\n"
        "  3. 'FINISH'       : 如果用户的问题此前已经被专家圆满回答，无需进一步派发。"
    )
    structured_llm = llm.with_structured_output(
        schrma=SupervisorRouteDecision,
        method="function_calling"
    )
    whole_messages = [SystemMessage(content=supervisor_system_prompt)]+state["messages"]
    logger.info(f"------------初始化信息拼接完成，准备调用LLM------------------------")
    res:SupervisorRouteDecision = structured_llm.invoke(whole_messages)
    logger.info(f"调用llm完成，结果输出：{res}")
    return {
        "next_worker":res.next_worker
    }

def route_from_supervisor(state: OverAllState)->Literal["dish_advisor", "order_manager",END]:
    next_worker =state.get("next_worker",'FINISH')
    logger.info(f"警察看分配哪个路{next_worker}")
    if next_worker =="FINISH" or not next_worker:
        return END
    return next_worker

def build_graph(checkpointer:Checkpointer):
    builder = StateGraph(OverAllState)
    builder.add_node("dish_advisor", dish_advisor_node)
    builder.add_node("order_manager", order_manager_node)
    builder.add_node("supervisor", supervisor_node)

    builder.add_edge(START,"supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        # {
        #     "dish_advisor":"dish_advisor",
        #     "order_manager":"order_manager"
        # }
    )
    builder.add_edge("dish_advisor","supervisor")
    builder.add_edge("order_manager","supervisor")

    return builder.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    checkpointer = MemorySaver()
    graph = build_graph(checkpointer)
    # print_graph_mermaid(graph, "test")

    payload={
        "messages":[HumanMessage(content="我第一次来这里吃饭，可以推荐一些菜品吗")],
        "next_worker": ""
    }
    config = {
        "configurable":{
            "thread_id":"CUSTOMER_01"
        }
    }
    # result = graph.invoke(payload, config=config)
    # logger.info(f"调用结果：{result}")

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
    res_2 = graph.invoke(scenario_2_input, config=cfg_2)
    print("\n最终对话产出:\n" + res_2["messages"][-1].content)
    print("=" * 65)