import json

from agent_study import print_conversation

# ==========================================
# 步骤 1：初始化对话历史（必须是有序列表，不能是字典！）
# ==========================================
# 为什么是列表？因为对话是多轮的，会有多次 user 和 assistant 交替出现
messages = [
    {"role": "system", "content": "你是一个贴心的旅行智能助手。"},
    {"role": "user", "content": "帮我查一下北京明天的天气。"},
]

# ==========================================
# 步骤 2：模拟大模型第一轮返回（决定调用工具）
# ==========================================
# 官方规范要点：
# 1. tool_calls 是一个列表（因为大模型一次可以同时调用多个工具！）
# 2. 字段名是 "id"（不是 tool_call_id）
# 3. 函数包装在 "function" 对象中，包含 "name" 和 "arguments"
# 4. arguments 必须是 JSON 字符串，不能是 Python 字典！
assistant_msg = {
    "role": "assistant",
    "content": None,
    "tool_calls": [
        {
            "id": "call_weather_9527",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": '{"city": "北京"}',  # 大模型返回的是 JSON 字符串
            },
        }
    ],
}
# 将大模型的决策加入历史记录
messages.append(assistant_msg)


# ==========================================
# 步骤 3：客户端在本地执行工具并回传结果
# ==========================================
def execute_tool_call(tool_call: dict) -> str:
    func_name = tool_call["function"]["name"]
    # 将 JSON 字符串解析为 Python 字典 //  '{"city": "北京"}'
    args = json.loads(tool_call["function"]["arguments"])
    print(f"正在执行工具: {func_name}, 解析后的参数: {args}")
    if func_name == "get_weather":
        city = args.get("city")
        # 本地模拟执行查询
        return f"{city} ☀ 晴天，气温 18~26°C，微风"
    return "未知工具"


# 从消息中取出工具调用指令
tool_call = assistant_msg["tool_calls"][0]
tool_result = execute_tool_call(tool_call)  # return a string

# 构造合法的 tool 角色回传报文
# 核心：必须带上 tool_call_id 与大模型的调用流水号绑定！
tool_msg = {
    "role": "tool",
    "tool_call_id": tool_call["id"],
    "content": tool_result,
}
messages.append(tool_msg)

# ==========================================
# 步骤 4：模拟大模型拿到工具结果后，给出最终回复
# ==========================================
final_assistant_msg = {
    "role": "assistant",
    "content": "北京明天的天气非常好，晴天，气温在 18~26°C 之间，伴有微风，适宜出行！",
}
messages.append(final_assistant_msg)


if __name__ == "__main__":
    print_conversation(messages)
