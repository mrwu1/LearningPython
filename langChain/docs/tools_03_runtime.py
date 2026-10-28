from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.runtime import Runtime

from docs.tools_02 import WeatherInput


@tool
def get_last_user_messages(runtime: Runtime) -> str:
    """GET THE MOST RECENT USER MESSAGES"""
    messages = runtime["messages"]

    #find the last human message
    for message in messages:
        if isinstance(message,HumanMessage):
            return message.content

    return 'no user messages found'

@tool
def get_user_preference(
        pref_name:str,
        runtime: Runtime,
):
    "get a user preference value"
    preferences = runtime.state.get("user_preferences",{})
    return preferences.get(pref_name,"no set")