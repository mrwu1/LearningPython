import os
import sqlite3
from typing import TypedDict, Annotated

from dotenv import find_dotenv, load_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.constants import START, END

load_dotenv(find_dotenv())
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import add_messages, StateGraph


# Layer 1: Conversational State Schema
class PersistentChatState(TypedDict):
    messages:Annotated[list[BaseMessage],add_messages]

# Layer 2: Model Setup & Chat Node
def get_llm():
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.0
    )

def conversational_agent_node(state:PersistentChatState):
    """Invokes LLM with full restored conversation history."""
    llm = get_llm()
    response = llm.invoke(state["messages"])
    return {"messages":[response]}

# Layer 3: Graph Assembly with Persistent Checkpointer
def build_persistent_graph(checkPointer:SqliteSaver):
    builder = StateGraph(PersistentChatState)
    builder.add_node("chat",conversational_agent_node)

    builder.add_edge(START,"chat")
    builder.add_edge("chat",END)

    return builder.compile(checkpointer=checkPointer)

# Layer 4: Execution & Snapshot Inspection
if __name__ == "__main__":
    #‼️ Create a persistent SQLite storage (in production, pass a file path or Postgres URI)
    db_connection = sqlite3.connect(":memory:",check_same_thread=False)
    checkpointer = SqliteSaver(db_connection)

    app = build_persistent_graph(checkpointer)

    # ‼️The thread_id identifies a single user session
    session_config = {"configurable":{"thread_id":"CUSTOMER_SESSION_88"}}

    # --- Turn 1: User discloses a secret preference ---
    turn_1_payload = {
        "messages":[HumanMessage(content="hello, my name is Alex, and my favorite fruit is Durian.")]
    }
    turn_1_response = app.invoke(turn_1_payload,config=session_config)
    print(f"[turn_1_response]:{turn_1_response['messages'][-1].content}\n")

    # --- Inspect the Checkpoint Snapshot created by Turn 1 ---
    snapshot_after_turn_1 = app.get_state(session_config)
    print("Under-The-Hood Checkpoint Snapshot Inspection:")
    print(f"  • Session Thread ID: {snapshot_after_turn_1.config['configurable']['thread_id']}")
    print(f"  • Checkpoint ID (UUIDv7): {snapshot_after_turn_1.config['configurable']['checkpoint_id']}")
    print(f"  • Checkpoint Namespace: {repr(snapshot_after_turn_1.config['configurable']['checkpoint_ns'])}")
    print(f"  • Next nodes waiting to run: {snapshot_after_turn_1.next}")
    print(f"  • Total messages persisted in DB: {len(snapshot_after_turn_1.values['messages'])}")

    # --- Turn 2: User asks a follow-up question without repeating context ---
    turn_2_payload={
        "messages":[HumanMessage(content="what is my name and what's my favorite fruit?")]
    }
    turn_2_response = app.invoke(turn_2_payload,config=session_config)
    print(f"turn_2_response: {turn_2_response['messages'][-1].content}")

    # --- Deep-Dive Inspection: Query SQLite directly to see LangGraph's internal tables ---
    cursor = db_connection.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("\n[DB Inspection] Tables automatically created by LangGraph:")
    for table in tables:
        print(f"  -> Table: {table[0]}")

    cursor.execute("SELECT thread_id, checkpoint_id, parent_checkpoint_id FROM checkpoints;")
    rows = cursor.fetchall()
    print("\n[DB Inspection] Checkpoint lineage stored in DB:")
    for row in rows:
        print(f"  • Thread: {row[0]} | Checkpoint: {row[1]} | Parent: {row[2]}")







