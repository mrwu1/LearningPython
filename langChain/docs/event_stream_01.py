from pprint import pprint

from langchain.agents import create_agent

from docs.utils import model


def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"It's always sunny in {city}!"


agent = create_agent(
    model=model,
    tools=[get_weather],
)

stream = agent.stream_events({
    "messages": [{"role": "user", "content": "What is the weather in HZ?"}],
}, version="v3")

# ⚠️：Use stream.messages when you want model output from each LLM call.
for message in stream.messages:

    for delta in message.text:
        print("----",delta, end="", flush=True)

    for delta in message.reasoning:
        print(f"[thinking] {delta}", end="", flush=True)


    for chunk in message.tool_calls:
        # {'type': 'tool_call_chunk', 'id': 'call_00_40BjLUgXG56ybPkl0hWd7958',
        # 'name': 'get_weather', 'args': 'ang', 'index': 0}
        print(f"tool call chunk: {chunk}")

    finalized = message.tool_calls.get()
    if finalized:
        print(f"finalized tool calls: {finalized}")

    # for call in stream.tool_calls:
    #     print(f"{call.tool_name}({call.input})")
    #     for delta in call.output_deltas:
    #         print(delta, end="", flush=True)
    #     print(call.output, call.error)


final_state = stream.output