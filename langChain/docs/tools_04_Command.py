from langchain.agents import AgentState
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import Command


class CustomState(AgentState):
    user_name: str

@tool
def set_user_name(new_name:str,runtime:ToolRuntime[None,CustomState]) -> Command:
    """set a user's name to new name"""
    return Command(
        update={
            "user_name": new_name,
            "messages":[
                ToolMessage(
                    content=f"user name set to {new_name}",
                    tool_call_id=runtime.tool_call_id,
                )
            ]
        }
    )
#⚠️：. Include a ToolMessage in the update so the model can see the result of the tool call: