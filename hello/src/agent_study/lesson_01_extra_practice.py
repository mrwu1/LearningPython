import json

from agent_study.print_conversation import print_conversation


messages = [
    {"role": "system", "content": "you are a helpful delivery assistant."},
    {
        "role": "user",
        "content": "where is my delivery that the number is SF123456789CN？",
    },
]
first_response_bymodel = {
    "role": "assistant",
    "content": None,
    "tool_calls": [
        {
            "id": "tool_logistics_001",
            "type": "function",
            "function": {
                "name": "query_logistics",
                "arguments": '{"tracking_number": "SF123456789CN"}',
            },
        }
    ],
}
# concat the new prompt to the existing messages
messages.append(first_response_bymodel)


# tool1:  define a tool function
def query_delivery(tracking_number: str):
    # TODO: code the real bussiness logic here.
    return f"单号 {tracking_number}：已到达【上海浦东转运中心】，正在派件中，快递员小李（13800138000）"


# fetch the delivery tool
def execute_tool_call(tool_call):
    func_name = tool_call["function"]["name"]
    args = json.loads(tool_call["function"]["arguments"])
    if func_name == "query_logistics":
        return query_delivery(args["tracking_number"])
    return None


# do
tool_call = first_response_bymodel["tool_calls"][0]
tool_result = execute_tool_call(tool_call)
print(tool_result)

tool_message = {
    "role": "tool",
    "tool_call_id": tool_call["id"],
    "content": tool_result,
}
# add it to history messages
messages.append(tool_message)

# new prompt from the model in the last round
last_prompt = {
    "role": "assistant",
    "content": "OK,BOSS! we find your delivery successful, it has been arrived Shanghai, and now it is delivering by delivery rider. Please keep you phone available.",
}
messages.append(last_prompt)

# print all the messages
print_conversation(messages)
tt = [
    {"role": "system", "content": "you are a helpful delivery assistant."},
    {
        "role": "user",
        "content": "where is my delivery that the number is SF123456789CN？",
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "tool_logistics_001",
                "type": "function",
                "function": {
                    "name": "query_logistics",
                    "arguments": '{"tracking_number": "SF123456789CN"}',
                },
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "tool_logistics_001",
        "content": "单号 SF123456789CN：已到达【上海浦东转运中心】，正在派件中，快递员小李（13800138000）",
    },
    {
        "role": "assistant",
        "content": "OK,BOSS! we find your delivery successful, it has been arrived Shanghai, and now it is delivering by delivery rider. Please keep you phone available.",
    },
]
