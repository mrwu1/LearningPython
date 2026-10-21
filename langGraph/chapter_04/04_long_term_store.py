import os
from typing import TypedDict, Annotated

from dotenv import find_dotenv, load_dotenv
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.checkpoint.memory import MemorySaver, InMemorySaver
from langgraph.constants import START, END
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from loguru import logger

load_dotenv(find_dotenv())
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import add_messages, StateGraph


# Layer 1: Schema Definition
class BaristaState(TypedDict):
    messages:Annotated[list[BaseMessage],add_messages]

# Layer 2: LLM Setup
def get_llm():
     return ChatOpenAI(
         model="deepseek-chat",
         api_key=os.getenv("DEEPSEEK_API_KEY"),
         base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
         temperature=0.0
     )
# Layer 3: Cognitive Node with Injected Long-Term Store
def barista_agent_node(state: BaristaState,config:RunnableConfig,*,store:BaseStore):
    # Extract identity from runtime configuration
    user_id = config.get("configurable",{}).get("user_id","anonymous")
    user_namespace = ("user",user_id,"profiles")

    # 1. Fetch persistent long-term memory for this user
    store_profile = state.get(user_namespace,"preferences")
    memory_context = ''
    if store_profile:
        memory_context = f"User Long-Term profiles:{store_profile}"
    else:
        logger.info("there is no profiles.")

    # 2. Assemble System Prompt with recalled memory
    system_instruction = (
        "you are an elite, highly personalized coffee shop barista assistant.\n"
        f"{memory_context}\n"
        "if you learn any new enduring dietary preferences, acknowledge them."
    )
    llm = get_llm()
    messages_to_send = [SystemMessage(content= system_instruction)]+state["messages"]
    response = llm.invoke(messages_to_send)
    logger.info(f"Assistant[barista_agent_node]: {response}")
    # 3. Simulate Long-Term Memory Extraction & Storage
    # In enterprise applications, this can be handled by an LLM tool call or structured extraction.
    latest_user_msg =state["messages"][-1].content
    if "lactose intolerant" in latest_user_msg.lower() or "oat milk" in latest_user_msg.lower():
        extracted_pref = {
            "milk_choice": "Oat Milk",
            "flavor": "Vanilla Syrup",
            "allergies": ["Lactose Intolerant"],
        }
        # ‼️：put it into the store
        store.put(user_namespace,"preferences",extracted_pref)
        logger.info(f"✅ [Memory Write] Successfully persisted profile into Store for [{user_id}]!")
    return {"messages":[response]}


 # Layer 4: Dual-Memory Graph Assembly
def build_dual_memory_graph(checkpointer:MemorySaver,store:BaseStore):
    builder  = StateGraph(BaristaState)
    builder.add_node("barista",barista_agent_node)

    builder.add_edge(START,"barista")
    builder.add_edge("barista",END)

    # ‼️：add two parameters for compile function
    return builder.compile(checkpointer=checkpointer,store=store)

# Layer 5: Cross-Session Verification Sandbox
if __name__ == "__main__":
    checkpointer = MemorySaver()
    #‼️：add a parameter: store
    store = InMemoryStore()
    app = build_dual_memory_graph(checkpointer,store)
    target_user = "user_charlie_77"
    # [day 1] Session 1: User establishes preference in a specific conversation thread
    session_1_config = {
        "configurable":{
            "thread_id":"THREAD_SESSION_1",
            "user_id": target_user
        }
    }
    turn_1 = app.invoke({
        "messages":[HumanMessage(content="hi, i'm charlie. i am lactose intolerant, so please always make my lattes with oat milk and vanilla syrup!")]
    },config=session_1_config)
    logger.info(f"Assistant[turn_1]: {turn_1['messages'][-1].content}\n")

    # [day 2] Session 2: NEXT DAY! Brand new conversation thread (Zero checkpointer history!)
    session_2_config = {
        "configurable":{
            "thread_id":"THREAD_SESSION_2",# Completely new thread! Checkpointer has 0 previous turns.
            "user_id":target_user
        }
    }
    # Verify that the short-term checkpointer has NO messages from Session 1
    new_thread_snapshot = app.get_state(session_2_config)
    logger.info(f"✅❌Verification: Messages in Session 2 checkpointer before query: {len(new_thread_snapshot.values.
                                                                                get('messages', []))}")
    # User places a simple order without repeating preferences
    turn_2 = app.invoke(
        {"messages":[HumanMessage(content="Can i get a large latte please?")]},
        config=session_2_config
    )
    logger.info(f"Assistant[turn_2]: {turn_2['messages'][-1].content}")