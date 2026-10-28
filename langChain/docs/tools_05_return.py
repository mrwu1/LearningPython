from langchain.tools import tool

# ✅ Return directly from a tool
# Set return direct on a tool to short-circuit the agent loop:
# the agent returns the tool’s output to the caller immediately,
# ⚠️ without sending it back through the model for further processing.
@tool(return_direct=True)
def fetch_order_status(order_id: str) -> str:
    """Fetch the current status of a customer order."""
    # In production, query your order management system here
    return f"Order {order_id} is shipped and will arrive in 2 days."

# ✅ Return an object (for example, a dict)
# when your tool produces structured data that the model should inspect.

@tool
def get_weather_data(city: str) -> dict:
    """Get structured weather data for a city."""
    return {
        "city": city,
        "temperature_c": 22,
        "conditions": "sunny",
    }


# ✅ Return multimodal content
# Tools are not limited to plain text.
# When the model supports multimodal tool results,
# the tool can return standard content blocks so the model receives text, images,
# and other media in one tool result.
@tool
def capture_screenshot() -> list[dict]:
    """Capture a screenshot of the current page."""
    return [
        {"type": "text", "text": "Screenshot of the current page:"},
        {"type": "image", "url": "https://example.com/page.png"},
    ]

# ✅ Return a Command
#Return a Command when the tool needs to update graph state (for example, setting user preferences or app state).
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command


@tool
def set_language(language: str, runtime: ToolRuntime) -> Command:
    """Set the preferred response language."""
    return Command(
        update={
            "preferred_language": language,
            "messages": [
                ToolMessage(
                    content=f"Language set to {language}.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )