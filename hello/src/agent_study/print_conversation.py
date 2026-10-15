# define a print_conversation function and export it


# ==========================================
# 步骤 5：打印整条会话生命周期
# ==========================================
def print_conversation(msg_list: list[dict]):
    print("=" * 60)
    print("📜 完整的 4 角色多轮对话生命周期报文")
    print("=" * 60)
    for idx, msg in enumerate(msg_list, 1):
        role = msg["role"]
        if role == "system":
            print(f"[{idx}] ⚙️ SYSTEM   : {msg['content']}")
        elif role == "user":
            print(f"[{idx}] 👤 USER     : {msg['content']}")
        elif role == "assistant":
            if msg.get("tool_calls"):
                call = msg["tool_calls"][0]
                print(
                    f"[{idx}] 🤖 ASSISTANT: [发起工具调用] 欲调用函数 `{call['function']['name']}` | 参数: {call['function']['arguments']} | 流水号: {call['id']}"
                )
            else:
                print(f"[{idx}] 🤖 ASSISTANT: {msg['content']}")
        elif role == "tool":
            print(
                f"[{idx}] 🛠️ TOOL      : [回传执行结果] 对应流水号 `{msg['tool_call_id']}` ➡️ 结果: {msg['content']}"
            )
    print("=" * 60)
