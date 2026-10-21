import os
import sys
from pathlib import Path
from typing import TypedDict, Literal, Annotated

from dotenv import find_dotenv, load_dotenv

# Ensure parent directory is in sys.path for graph_utils import
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


class MultiAgentState(TypedDict):
    messages:Annotated[list[BaseMessage],add_messages]
    next_worker:str

 # Structured output contract enforced on the Supervisor
class SupervisorRouteDecision(BaseModel):
    next_worker: Literal["dish_advisor", "order_manager", "FINISH"] = Field(
        ...,
        description="The next specialized agent to handle the query, or FINISH if fully answered."
    )
    routing_reason: str = Field(..., description="Brief rationale for this delegation choice.")

def get_llm():
        return ChatOpenAI(
            model="deepseek-chat",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=0.0
        )
# specialist one - dish_advisor
def dish_advisor_worker(state:MultiAgentState)->dict:

    llm = get_llm()
    system_prompt = (
        "You are a Sky Takeout gourmet advisor. you specialize in healthy,delicious meal recommendations"
        "Recommend suitable meals base on customer's request concisely in 2 sentences."
    )
    # + [left]+[right] = [left,right]
    response = llm.invoke([SystemMessage(content=system_prompt)]+state["messages"])
    return{
        "messages":[AIMessage(content=f"[Dish advisor]:{response.content}")],
        "next_worker":"FINISH"
    }

def order_manager_worker(state: MultiAgentState):
        """Specialist 2: Handles logistics tracking and delivery dispatch."""

        # Simulating internal order database query
        courier_status = "Courier Xiao Wang has picked up your meal. Current distance: 1.2 km, ETA: 7 mins."

        system_prompt = (
            f"You are the Sky Takeout Logistics Manager. Current delivery telemetry: '{courier_status}'. "
            "Answer the customer politely and give them reassurance in 2 concise sentences."
        )
        llm = get_llm()
        response = llm.invoke([SystemMessage(content=system_prompt)] + state["messages"])

        return {
            "messages": [AIMessage(content=f"[Order Manager]: {response.content}")],
            "next_worker": "FINISH"
            # Signal work completed
        }
# ‼️‼️ - the main brain:
def supervisor_node(state:MultiAgentState)->dict:
    supervisor_system_prompt = (
        "You are the Central Orchestration Supervisor for Sky Takeout.\n"
        "Your sole responsibility is to route the conversation to the most qualified specialist:\n"
        "  1. 'dish_advisor': For meal suggestions, dish info, calories, diet preferences.\n"
        "  2. 'order_manager': For order delivery status, ETA, courier tracking, address changes.\n"
        "  3. 'FINISH': If the user has already received a satisfactory final answer."
    )
    llm = get_llm()
    structured_llm = llm.with_structured_output(SupervisorRouteDecision,method="function_calling")
    whole_messages = ([SystemMessage(content=supervisor_system_prompt)]
                     + state["messages"])
    logger.info(f"f:before invoking the model:{whole_messages}")
    decision:SupervisorRouteDecision = structured_llm.invoke(whole_messages)

    logger.info(f"⚠️：[Supervisor] Routing decision -> '{decision.next_worker}' | Reason: {decision.routing_reason}")
    return {"next_worker": decision.next_worker}

# after executing the main brain - dispatch tasks to specialist
def route_from_supervisor(state:MultiAgentState)->Literal["dish_advisor","order_manager","__end__"]:
    target = state.get("next_worker","FINISH") #`dict.get(key, default)` Python 字典原生 API：
    if target =="FINISH" or not target: # empty
        return END
    return target

def build_supervisor_graph():
    builder = StateGraph(MultiAgentState)

    # Register nodes
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("dish_advisor", dish_advisor_worker)
    builder.add_node("order_manager", order_manager_worker)

    builder.add_edge(START,"supervisor")
    builder.add_conditional_edges("supervisor",route_from_supervisor)

    # return back to supervisor
    builder.add_edge("dish_advisor","supervisor")
    builder.add_edge("order_manager","supervisor")

    return builder.compile(checkpointer=MemorySaver())

if __name__ == "__main__":
    app = build_supervisor_graph()
    print_graph_mermaid(app,"01")
    scenario_1_input = {
        "messages": [HumanMessage(content="I want a healthy low-calorie dinner with salmon under 500 kcal.")],
        "next_worker": ""
    }
    cfg_1 = {"configurable": {"thread_id": "SESSION_MULTI_01"}}
    res_1 = app.invoke(scenario_1_input, config=cfg_1)
    logger.info(f"[scenario_1]:{res_1}")
    logger.info(res_1["messages"][-1].content)
    logger.info("-------------------------------------------------------------------")
    scenario_2_input = {
        "messages": [HumanMessage(content="Where is my food? It's raining outside, did the courier get lost?")],
        "next_worker": ""
    }
    cfg_2 = {"configurable": {"thread_id": "SESSION_MULTI_02"}}
    res_2 = app.invoke(scenario_2_input, config=cfg_2)

    logger.info(res_2["messages"][-1].content)
