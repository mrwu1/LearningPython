# flowchart TD
#         Start["开始：用户输入问题"] --> Step["Step = 1"]
#         Step --> Check{"Step > max_iterations ?"}
#         Check -->|是| Fail["🚨 触发熔断！强行终止循环"]
#         Check -->|否| CallLLM["调用大模型 (传入当前 messages + tools)"]
#         CallLLM --> HasTools{"模型返回了 tool_calls 吗？"}
#         HasTools -->|否 (没有)| End["🎉 任务完成！直接输出最终文本"]
#         HasTools -->|是 (有)| Exec["通过 Registry 动态执行本地工具"]
#         Exec --> Append["将 assistant(带tool_calls) 和 tool(结果) 追加进 messages"]
#         Append --> Next["Step = Step + 1"]
#         Next --> Check


import json


# ==============================================================================
# 1. 本地真实工具函数（业务执行器）
# ==============================================================================
def get_employee_salary(emp_id: str) -> str:
    """模拟查询员工月薪"""
    db = {"E001": 20000.0, "E002": 15000.0}
    salary = db.get(emp_id, 8000.0)  # value
    return json.dumps({"emp_id": emp_id, "monthly_salary": salary})  # 转为json字符串


def calculate_tax(income: float) -> str:
    """模拟计算个人所得税"""
    if income <= 5000:
        tax = 0.0
    else:
        tax = round((income - 5000) * 0.1, 2)
    return json.dumps({"income": income, "tax": tax})


def execute_tool(func_name: str, arguments_json: str) -> str:
    """简易工具分发器"""
    args = json.loads(arguments_json)
    if func_name == "get_employee_salary":
        return get_employee_salary(args["emp_id"])
    elif func_name == "calculate_tax":
        return calculate_tax(args["income"])
    return f"未知工具: {func_name}"


# ==============================================================================
# 2. 模拟大模型大脑（根据上下文动态决策）
# ==============================================================================
def mock_llm_react_brain(messages: list[dict]) -> dict:
    """
    模拟大模型的三轮思考：
    • Round 1：看到只有用户提问，决策调用 get_employee_salary
    • Round 2：看到查到了 20000 薪资，决策调用 calculate_tax
    • Round 3：看到个税已计算完成，综合推导后直接给出最终回答，不再调用工具
    """
    last_msg = messages[-1]

    # 情况 A：如果上一条是 user 的提问，模型第一步是去查工资
    if last_msg["role"] == "user":
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_salary_001",
                    "type": "function",
                    "function": {
                        "name": "get_employee_salary",
                        "arguments": '{"emp_id": "E001"}',
                    },
                }
            ],
        }

    # 情况 B：如果上一条是查工资的 tool 结果，模型第二步去算个税
    if last_msg["role"] == "tool" and last_msg["tool_call_id"] == "call_salary_001":
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_tax_002",
                    "type": "function",
                    "function": {
                        "name": "calculate_tax",
                        "arguments": '{"income": 20000.0}',
                    },
                }
            ],
        }

    # 情况 C：如果上一条是算个税的 tool 结果，信息已经完整，模型给出最终自然语言解答！
    if last_msg["role"] == "tool" and last_msg["tool_call_id"] == "call_tax_002":
        return {
            "role": "assistant",
            "content": "员工 E001 的税前月薪为 20,000 元，应缴个税 1,500 元，税后实际到手收入为 18,500 元。",
            "tool_calls": None,
        }

    return {"role": "assistant", "content": "未能理解当前状态。", "tool_calls": None}


# ==============================================================================
# 3. 原生 ReAct 引擎主循环（带熔断保护）
# ==============================================================================
def run_react_agent(query: str, max_iterations: int = 5) -> str:
    print(f"\n🚀 [Agent 启动] 收到任务: '{query}'")
    print(f"🛡️  [安全配置] 最大思考迭代步数 (max_iterations): {max_iterations}")

    messages = [
        {"role": "system", "content": "你是一个严谨的企业财务分析智能体。"},
        {"role": "user", "content": query},
    ]

    step = 1

    # 核心状态机循环：只要没触发熔断就一直运行
    while step <= max_iterations:
        print(f"\n--- [第 {step} 步迭代思考] ---")

        # 1. 询问大模型大脑
        llm_response = mock_llm_react_brain(messages)

        # 2. 判断模型是否想调用工具
        tool_calls = llm_response.get("tool_calls")

        # 👉 分支 1：模型没有调用工具，给出了最终答案！
        if not tool_calls:
            final_content = llm_response.get("content")
            print(f"🎉 [任务圆满完成] 大模型输出最终答案:\n{final_content}")
            messages.append(llm_response)
            return final_content

        # 👉 分支 2：模型决定调用工具，执行 Action
        # 注意：先把 assistant 消息（带 tool_calls）追加进历史
        messages.append(llm_response)

        for call in tool_calls:
            call_id = call["id"]
            func_name = call["function"]["name"]
            arguments_str = call["function"]["arguments"]

            print(f"🤖 模型决策 (Thought) ➡️ 需调用工具: `{func_name}`")
            print(f"📥 传入参数: {arguments_str}")

            # 本地执行真实代码 (Action)
            result = execute_tool(func_name, arguments_str)
            print(f"🛠️ 执行结果 (Observation): {result}")

            # 组装 tool 消息并追加到历史 (回传观察结果)
            tool_msg = {
                "role": "tool",
                "tool_call_id": call_id,
                "content": result,
            }
            messages.append(tool_msg)

        step += 1

    # 超过最大步数，触发 Anthropic 强调的熔断保护！
    print(
        f"\n🚨 [触发熔断报警] 当前任务思考已达到上限 {max_iterations} 步，强制退出！防止死循环与Token浪费！"
    )
    return "抱歉，由于任务复杂度过高或陷入死循环，已被系统安全熔断中断。"


# ==============================================================================
# 4. 运行验证
# ==============================================================================
if __name__ == "__main__":
    print("================== 实验 1：正常多步 ReAct 闭环 ==================")
    run_react_agent("请帮我计算员工 E001 的税后月薪是多少？", max_iterations=5)

    print("\n================== 实验 2：触发熔断保护测试 ==================")
    # 故意把最大步数设为 1，观察熔断机制如何生效
    run_react_agent("请帮我计算员工 E001 的税后月薪是多少？", max_iterations=1)
