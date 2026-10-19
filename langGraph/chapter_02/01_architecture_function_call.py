import os
from typing import Annotated, TypedDict

from dotenv import load_dotenv

load_dotenv()
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.graph import add_messages, StateGraph
from langgraph.prebuilt import InjectedState, ToolNode
from loguru import logger

from graph_utils import print_graph_mermaid


# 1. Define Secure Enterprise Tool
@tool
def query_takeout_order(
        order_id:str,
        current_user_id:Annotated[str,InjectedState("authenticated_user_id")]
)->str:
    """Retrieve takeout order details for the authenticated customer."""
    # Mock database query with zero-trust safety check
    return (
        f"Order {order_id} Details: 1x Cheese Pizza, 1x Cola. "
        f"Status: In Delivery. Verified Owner: {current_user_id}."
    )


# 2. Define Agent State
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage],add_messages]
    authenticated_user_id:str

# 3. Model Setup & Agent Node
def get_deepseek_model():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    # deepseek-chat represents DeepSeek-V3 with native function calling support
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=api_key,
        base_url=base_url,
        temperature=0.0,
    )

def agent_decision_node(state: AgentState) -> dict:
        model = get_deepseek_model()
        model_with_tools = model.bind_tools([query_takeout_order])
        logger.info(f"model_with_tools:{model_with_tools}")
        response = model_with_tools.invoke(state["messages"])
        logger.info(f"the model response data is: {response}")
        # 解析：new_messages = add_messages(current_state["messages"], [response])
        # AImessage:LangChain 规范的所有 ChatModel（对话大模型），其 invoke() 方法的返回值，出厂默认就封装成了
        #   langchain_core.messages.AIMessage 对象！
        return {"messages": [response]}

# 4. Graph Assembly
def build_secure_tool_graph():
    builder = StateGraph(AgentState)

    # Register Nodes
    builder.add_node("agent", agent_decision_node)
    # ToolNode automatically handles InjectedState resolution!
    builder.add_node("tools", ToolNode([query_takeout_order]))

    # Static sequence: START -> agent -> tools -> END
    # (Next lesson we will introduce conditional looping edges!)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", "tools")
    builder.add_edge("tools", END)

    return builder.compile()

# 5. Verification & Deep-Dive Inspection
# ==========================================
if __name__ == "__main__":
        # --- Part 1: Schema Security Inspection ---
        print("Step 1: Inspecting Tool Schema sent to DeepSeek:")
        openai_schema = convert_to_openai_tool(query_takeout_order)
        exposed_params = openai_schema["function"]["parameters"]["properties"]
        print(f"Parameters exposed to LLM: {list(exposed_params.keys())}")

        # --- Part 2: Live Execution with DeepSeek ---
        app = build_secure_tool_graph()

        # User input contains only the order_id, attempting to inquire about the order
        initial_payload: AgentState = {
            "messages": [HumanMessage(content="Hi, please check the status of my order SKY-8899.")],
            "authenticated_user_id": "USR-VIP-CHEN-2026"
        }

        print("\nStep 2: Executing Secure Agent Graph ...")
        final_state = app.invoke(initial_payload)

        print("\n" + "=" * 65)
        print("Step 3: Final Conversation History:")
        for msg in final_state["messages"]:
            print(f"[{msg.__class__.__name__}]: {msg.content or f'ToolCalls: {msg.tool_calls}'}")
        print("=" * 65)
        print_graph_mermaid(app, "01")