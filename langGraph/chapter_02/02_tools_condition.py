import os
import sys
from pathlib import Path
from typing import TypedDict, Annotated, Callable

from dotenv import load_dotenv, find_dotenv  # 👈 1. 导入 find_dotenv

# 👈 2. 自动向上递归寻找 .env，彻底解决找不到 Key 的问题！
load_dotenv(find_dotenv())

# 👈 3. 自动将根目录加进 sys.path，保证 graph_utils 无论在哪都能成功 import！
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


# Layer 1: Infrastructure Layer (Model Factory)
class LLMClientFactory:
    """Enterprise Factory managing model lifecycle and connections."""
    _model_instance:ChatOpenAI|None = None

    @classmethod
    def get_chat_model(cls)-> ChatOpenAI:
        if cls._model_instance is None:
            api_key = os.getenv("DEEPSEEK_API_KEY")
            base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            cls._model_instance = ChatOpenAI(
                model="deepseek-chat",
                api_key= api_key,
                base_url=base_url,
                temperature = 0.0
            )
            #avoid create a instance each time.
        return cls._model_instance
# Layer 2: Domain State & Business Tools
@tool
def get_chef_specials(cuisine_category:str)->str:
    """Retrieve top-rated chef recommendation dishes for a specific cuisine category."""
    # Mocking real database / microservice lookup
    logger.info("🔧：start to execute this tool")
    if "italian" in cuisine_category.lower():
        return "1. Black Truffle Pasta ($28), 2. Wood-Fired Margherita Pizza ($18)."
    elif "sichuan" in cuisine_category.lower():
        return "1. Mapo Tofu ($14), 2. Kung Pao Chicken ($16)."
    return "Chef's Special Tasting Menu ($45)."

class ReActAgentState(TypedDict):
    messages:Annotated[list[BaseMessage],add_messages]

# Layer 3: Pure Business Node Factory
def create_reasoning_node(model:Runnable)->Callable[[ReActAgentState],dict]:
    """Factory injecting pre-configured tool-bound model into the agent node."""
    def agent_node(state:ReActAgentState)->dict:
        response = model.invoke(state["messages"])
        logger.info(f"✅we get the response from llm:{response}")
        return {"messages":[response]}
    return agent_node

# Layer 4: Graph Assembly (The ReAct Cyclic Engine)
def build_react_agent_graph()->Runnable:
    # 1. Prepare tool collection and pre-bind with model
    tools =[get_chef_specials]
    base_llm = LLMClientFactory.get_chat_model()
    model_with_tools = base_llm.bind_tools(tools)

    # 2. Initialize StateGraph
    builder = StateGraph(ReActAgentState)
    builder.add_node("agent",cr eate_reasoning_node(model_with_tools))
    # ‼️‼️： register a node "tools" which is same as tools_condition
    builder.add_node("tools",ToolNode(tools))
    mklk
    builder.add_edge(START,"agent")

    # ⚠️：Dynamic branch: tools_condition decides between 'tools' or END
    #  负责决定这辆车从 agent 站开出来之后，该去哪里！
    builder.add_conditional_edges(
        source="agent",
        path=tools_condition
    )

    # ✅：after check the tool and execute it.
    builder.add_edge("tools","agent")

    return builder.compile()

#test
if __name__=="__main__":
    app = build_react_agent_graph()

    # print_graph_mermaid(app,'02')

    initial_payload: ReActAgentState = {
        "messages": [HumanMessage(content="What do you recommend for Italian food tonight?")]
    }
    final_state = app.invoke(initial_payload)
    logger.info(f"✅final_state:{final_state}")














