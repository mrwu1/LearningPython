# State injection
# Tools access graph state through ToolRuntime. ✅
# See Access context for state, context, store, and streaming APIs.✅✅✅

from langchain.tools import tool, ToolRuntime

@tool
def get_message_count(runtime: ToolRuntime) -> str:
    """Get the number of messages in the conversation."""
    messages = runtime.state["messages"]
    return f"There are {len(messages)} messages."