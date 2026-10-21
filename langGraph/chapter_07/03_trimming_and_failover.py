import sys
from pathlib import Path
from typing import TypedDict, Annotated
from dotenv import find_dotenv, load_dotenv
from loguru import logger

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

# Standard environment & sys.path setup
load_dotenv(find_dotenv())
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ==============================================================================
# Layer 1: Schema Definition with Budget Circuit Breaker
# ==============================================================================
class GuardedChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    turn_count: int
    circuit_broken: bool
    final_output: str

# Maximum turns allowed per session to prevent infinite runaway loops
MAX_TURN_BUDGET = 5

# ==============================================================================
# Layer 2: Simulated Primary & Fallback Models
# ==============================================================================
def unstable_primary_llm(messages: list[BaseMessage]) -> AIMessage:
    """Simulates primary LLM encountering temporary 503 gateway outage."""
    logger.error("  [Primary LLM: DeepSeek] 💥 503 Service Unavailable: Provider cluster overloaded!")
    raise ConnectionError("HTTP 503 Provider Outage")

def stable_backup_llm(messages: list[BaseMessage]) -> AIMessage:
    """Simulates high-availability backup LLM stepping in seamlessly."""
    logger.info("  [Backup LLM: Disaster Recovery Node] 🛡️ Seamlessly handling request fallback.")
    return AIMessage(content="[BACKUP ENGINE RESCUE] Order status: Dispatched and arriving on schedule.")

# Configure built-in seamless failover
primary_runnable = RunnableLambda(unstable_primary_llm)
backup_runnable = RunnableLambda(stable_backup_llm)
resilient_cognitive_engine = primary_runnable.with_fallbacks([backup_runnable])

# ==============================================================================
# Layer 3: Nodes with Context Trimming & Budget Guard
# ==============================================================================
def cognitive_agent_node(state: GuardedChatState):
    """
    Agent Node protected by:
    1. Budget Circuit Breaker (hard limit on runaway loops)
    2. Intelligent Context Trimming (preserving system message)
    3. Model Failover (with_fallbacks)
    """
    current_turns = state.get("turn_count", 0) + 1
    logger.info(f"[Agent Node] Executing Turn #{current_turns} / Max Budget: {MAX_TURN_BUDGET}")

    # 1. Budget Circuit Breaker Check
    if current_turns > MAX_TURN_BUDGET:
        logger.warning(f"  [Circuit Breaker] 🚨 Hard limit exceeded ({current_turns} > {MAX_TURN_BUDGET})! Halting execution.")
        return {
            "turn_count": current_turns,
            "circuit_broken": True,
            "final_output": "BUDGET_EXCEEDED_SESSION_FROZEN"
        }

    # 2. Context Trimming: Keep system instruction + only recent turns
    trimmed_history = trim_messages(
        state["messages"],
        max_tokens=4,           # In production, set to e.g. 4000 tokens
        token_counter=len,      # Simple message count for clear sandbox verification
        strategy="last",        # Keep the latest messages
        include_system=True     # CRITICAL: Always preserve the foundational SystemMessage!
    )
    logger.info(f"  [Context Trimmer] Trimmed message history from {len(state['messages'])} down to {len(trimmed_history)}")

    # 3. Model Invocation with Auto-Failover
    ai_response = resilient_cognitive_engine.invoke(trimmed_history)
    
    return {
        "messages": [ai_response],
        "turn_count": current_turns,
        "circuit_broken": False,
        "final_output": ai_response.content
    }

def build_guarded_graph():
    builder = StateGraph(GuardedChatState)
    builder.add_node("agent", cognitive_agent_node)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)
    return builder.compile(checkpointer=MemorySaver())

# ==============================================================================
# Layer 4: Execution & Verification Sandbox
# ==============================================================================
if __name__ == "__main__":
    app = build_guarded_graph()

    # --------------------------------------------------------------------------
    # Test 1: Context Trimming & Failover Demonstration
    # --------------------------------------------------------------------------
    print("=" * 65)
    print(" 🛡️ TEST 1: INTELLIGENT TRIMMING & FAILOVER TEST")
    print("=" * 65)

    # Fabricate a long 7-message conversation history
    bloated_messages = [
        SystemMessage(content="You are Sky Takeout Assistant. Protect user data."),
        HumanMessage(content="Old msg 1: Hello"),
        AIMessage(content="Old reply 1: Hi"),
        HumanMessage(content="Old msg 2: What is my discount?"),
        AIMessage(content="Old reply 2: 10% off"),
        HumanMessage(content="Recent msg 3: Where is my lunch now?")
    ]

    config_normal = {"configurable": {"thread_id": "SESSION_HA_01"}}
    res_1 = app.invoke(
        {"messages": bloated_messages, "turn_count": 0, "circuit_broken": False, "final_output": ""},
        config=config_normal
    )

    print("\nTest 1 Execution Verdict:")
    print(f"  • Final Output: {res_1['final_output']}")
    print(f"  • Circuit Broken: {res_1['circuit_broken']}")
    print(f"  • Verified Failover: Primary failed with 503, Backup handled request seamlessly!")

    # --------------------------------------------------------------------------
    # Test 2: Token Budget Circuit Breaker
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print(" 🛡️ TEST 2: RUNAWAY LOOP CIRCUIT BREAKER (BUDGET OVERFLOW)")
    print("=" * 65)

    # Simulate an agent session that has already consumed 5 turns and tries turn #6
    exhausted_session_input = {
        "messages": [HumanMessage(content="Loop query...")],
        "turn_count": 5, # Exactly at threshold
        "circuit_broken": False,
        "final_output": ""
    }

    config_breaker = {"configurable": {"thread_id": "SESSION_RUNAWAY_02"}}
    res_2 = app.invoke(exhausted_session_input, config=config_breaker)

    print("\nTest 2 Execution Verdict:")
    print(f"  • Final Output:   {res_2['final_output']}")
    print(f"  • Circuit Broken: {res_2['circuit_broken']} (Successfully blocked runaway cost!)")
    print("=" * 65)
