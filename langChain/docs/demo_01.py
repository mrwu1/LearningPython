from pprint import pprint

from langchain.chat_models import init_chat_model
from langchain.tools import tool


# messages = [
#     SystemMessage(
#         content=(
#             "你负责从顾客描述中提取售后诉求。"
#             "仅提取明确提供的信息，缺失的信息不要猜测。"
#             "不要判断退款是否获批。"
#         )
#     ),
#     HumanMessage(
#         content="订单 A1023 少送了一份米饭，我要退款。"
#     ),
# ]
# for message in messages:
#     print(type(message).__name__)
#     print(message.content)
#     print()
@tool
def get_weather(location: str) -> str:
    """Get the weather at a location."""
    return f"It's sunny in {location}."

model = init_chat_model(
    "deepseek-flash",
    model_provider="deepseek",
    # Kwargs passed to the model:
    base_url="https://api.deepseek.com",
    api_key="sk-f8f7bf1c05404adb96717f0c929a6c46",
    temperature=0.7,
    timeout=30,
    max_tokens=1000,
    max_retries=6,  # Default; increase for unreliable networks
)
model_with_tools = model.bind_tools([get_weather])
conversation = [
    {"role": "system", "content": "You are a helpful assistant that provides the weather information"},
    {"role": "user", "content": "杭州今天天气怎么样？"},
]

response = model_with_tools.invoke(conversation)
pprint(response)
for tool_call in response.tool_calls:
    # View tool calls made by the model
    print(f"Tool: {tool_call['name']}")
    print(f"Args: {tool_call['args']}")