# Customizing agent memory
# By default, agents use ✅ AgentState to manage short term memory, specifically the conversation history via a messages key.
# You can extend AgentState to add additional fields. Custom state schemas are passed to create_agent using the state_schema parameter.
from langchain.agents import AgentState, create_agent
from langgraph.checkpoint.memory import InMemorySaver

from docs.utils import model


# ‼️
class CustomAgentState(AgentState):
    user_id:str
    preferences:dict

agent = create_agent(
    model=model,
    tools=[],#[get_user_info]
    state_schema=CustomAgentState,
    checkpointer=InMemorySaver(),
)

# Custom state can be passed in invoke
result = agent.invoke(
    {
        "messages": [{"role": "user", "content": "Hello"}],
        "user_id": "user_123",
        "preferences": {"theme": "dark"}
    },
    {"configurable": {"thread_id": "1"}})