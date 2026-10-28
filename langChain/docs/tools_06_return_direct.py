from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI

from docs.utils import model


@tool(return_direct=True)
def fetch_order_status(order_id: str) -> str:
    """Fetch the current status of a customer order."""
    # In production, query your order management system here
    return f"Order {order_id} is shipped and will arrive in 2 days."


agent = create_agent(
    model=model,
    tools=[fetch_order_status],
)

result = agent.invoke({
    "messages": [{"role": "user", "content": "What is the status of order #12345?"}]
})
print(result)
# The agent returns the tool output directly without another LLM call:
# "Order 12345 is shipped and will arrive in 2 days."
# Behavior:
# The tool executes normally and its output is wrapped in a ToolMessage.
#⚠️：The agent stops looping and returns the tool’s output as the final response, bypassing any additional model call.
# Multiple parallel tool calls: When the model calls several tools in one step, all of them execute first. After all tools finish, the agent routes to END only if every tool in that batch has return_direct=True. The final response includes the ToolMessage outputs of every tool that was called in that step.

# Use this when:
# The tool’s output is the complete, user-ready answer (for example, a lookup that returns a ready-to-display result).
# You want to avoid an extra model call when no additional reasoning is needed.
# You need deterministic, unmodified output: the model cannot rephrase, summarize, or act on the tool result.