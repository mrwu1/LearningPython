from typing import Callable

from langchain.agents import create_agent
from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from docs.utils import model


# Handle tool errors using LangChain agent middleware to retry failed tool calls or return custom error messages:
# ✅：@wrap_tool_call

@wrap_tool_call
def handle_tool_errors(
        request:ToolCallRequest,
        handler:Callable[[ToolCallRequest], ToolMessage],
):
    """convert tool exceptions into ToolMessages the modal can handle"""
    try:
        return handler(request)
    except Exception as e:
        return ToolMessage(
            content=f"Tool error: Please check your input and try again. ({e})",
            tool_call_id = request.tool_call["id"]
        )

agent = create_agent(
    model=model,
    tools=[],
    middleware=[handle_tool_errors]
)