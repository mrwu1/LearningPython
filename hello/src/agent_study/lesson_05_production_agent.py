import json
from pydantic import BaseModel, Field


# ==============================================================================
# 1. 业务工具参数模型（Pydantic V2 契约）
# ==============================================================================
class EmpQueryArgs(BaseModel):
    emp_name: str = Field(..., description="要查询的员工真实姓名，如 '张三'")


class DeptQueryArgs(BaseModel):
    department: str = Field(..., description="要查询进度的部门名称，如 'AI实验室'")


# ==============================================================================
# 2. 工业级生产 Agent 引擎类
# ==============================================================================
class ProductionAgent:
    def __init__(self, system_prompt: str, max_iterations: int = 5):
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        # 内部路由表：存储工具名与 (函数, 参数模型, 描述) 的映射
        self._tools = {}

    def register_tool(self, name: str, description: str, args_model: type[BaseModel]):
        """装饰器：向 Agent 注册一个业务工具"""

        def decorator(func):
            self._tools[name] = {
                "func": func,
                "args_model": args_model,
                "description": description,
            }
            return func

        return decorator

    def get_tools_schema(self) -> list[dict]:
        """导出符合 OpenAI 规范的 tools 契约列表"""
        schemas = []
        for name, info in self._tools.items():
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": info["description"],
                        "parameters": info["args_model"].model_json_schema(),
                    },
                }
            )
        return schemas

    def execute_tool(self, name: str, arguments_json: str) -> str:
        """通过 Pydantic 安全校验并动态执行本地工具"""
        if name not in self._tools:
            return f"错误：未注册的工具 '{name}'"

        tool_info = self._tools[name]
        try:
            # 核心：使用 Pydantic 解析并校验大模型生成的参数
            validated_args = tool_info["args_model"].model_validate_json(arguments_json)
            # 执行真实函数并转为字符串输出
            return str(tool_info["func"](validated_args))
        except Exception as e:
            return f"工具执行异常: {e}"

    def mock_llm_brain(self, messages: list[dict]) -> dict:
        """
        模拟大模型的动态思考过程：
        • Round 1：看到用户问张三的项目，第一步调用 query_employee 查询张三所在部门
        • Round 2：拿到部门是 AI实验室，第二步调用 query_department_project 查询部门项目
        • Round 3：拿到项目和进度，给出最终的自然语言总结解答
        """
        last_msg = messages[-1]

        # 第 1 轮决策：看到用户提问
        if last_msg["role"] == "user":
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_emp_101",
                        "type": "function",
                        "function": {
                            "name": "query_employee",
                            "arguments": '{"emp_name": "张三"}',
                        },
                    }
                ],
            }

        # 第 2 轮决策：拿到张三的部门结果
        if last_msg["role"] == "tool" and last_msg["tool_call_id"] == "call_emp_101":
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_dept_202",
                        "type": "function",
                        "function": {
                            "name": "query_department_project",
                            "arguments": '{"department": "AI实验室"}',
                        },
                    }
                ],
            }

        # 第 3 轮决策：信息齐备，输出最终答复
        if last_msg["role"] == "tool" and last_msg["tool_call_id"] == "call_dept_202":
            return {
                "role": "assistant",
                "content": "根据系统最新数据，张三目前就职于【AI实验室】，正在主导核心项目【自研企业级Agent引擎】，当前整体研发进度为 95%。",
                "tool_calls": None,
            }

        return {
            "role": "assistant",
            "content": "未能识别的会话状态。",
            "tool_calls": None,
        }

    def run(self, user_query: str) -> str:
        """启动透明、可控的 ReAct 状态机主循环"""
        print(f"\n🚀 [Agent 引擎启动] 接收到任务: '{user_query}'")
        print(f"🛡️  [安全配置] 最大迭代熔断阈值: {self.max_iterations}")

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_query},
        ]

        step = 1
        while step <= self.max_iterations:
            print(f"\n--- [第 {step} 步思考与调度] ---")

            # 1. 向大模型获取决策  - 切换 🚗
            llm_response = self.mock_llm_brain(messages)
            tool_calls = llm_response.get("tool_calls")  # ✅✅❌❌

            # 分支 A：模型推导完成，直接返回最终答案
            if not tool_calls:
                final_answer = llm_response.get("content")
                print(
                    f"🎯 [状态机终态达成] 耗时 {step} 步，输出最终答案:\n{final_answer}"
                )
                messages.append(llm_response)
                return final_answer

            # 分支 B：模型决策调用工具
            messages.append(llm_response)

            for call in tool_calls:
                call_id = call["id"]
                func_name = call["function"]["name"]
                args_str = call["function"]["arguments"]

                print(
                    f"🤖 决策 (Thought) ➡️ 欲调用工具: `{func_name}` | 绑定流水号: {call_id}"
                )
                print(f"📥 提取入参: {args_str}")

                # 本地执行业务代码
                obs = self.execute_tool(func_name, args_str)
                print(f"🛠️ 观察结果 (Observation): {obs}")

                # 将工具执行结果作为 tool 角色回传给大模型
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": obs,
                    }
                )

            step += 1

        print(f"\n🚨 [触发熔断保护] 达到最大限制步数 {self.max_iterations}，强制终止！")
        return "抱歉，由于任务过深或未能在预期步数内收敛，Agent 已触发安全熔断机制。"


# ==============================================================================
# 3. 业务工具绑定与运行测试
# ==============================================================================
# 初始化 Agent 实例
agent = ProductionAgent(
    system_prompt="你是一个严谨的企业信息查询助手，必须基于真实工具数据给出客观、准确的答复。",
    max_iterations=5,
)


# 注册工具 1：查员工
@agent.register_tool(
    name="query_employee",
    description="根据员工姓名查询其工号和所在部门",
    args_model=EmpQueryArgs,
)
def query_employee(args: EmpQueryArgs) -> str:
    if args.emp_name == "张三":
        return json.dumps({"id": "E1001", "department": "AI实验室"}, ensure_ascii=False)
    return json.dumps({"error": "未找到该员工"}, ensure_ascii=False)


# 注册工具 2：查部门项目
@agent.register_tool(
    name="query_department_project",
    description="根据部门名称查询该部门当前的重点项目及完成进度",
    args_model=DeptQueryArgs,
)
def query_department_project(args: DeptQueryArgs) -> str:
    if args.department == "AI实验室":
        return json.dumps(
            {"current_project": "自研企业级Agent引擎", "progress": "95%"},
            ensure_ascii=False,
        )
    return json.dumps({"error": "未找到该部门的项目信息"}, ensure_ascii=False)


if __name__ == "__main__":
    # 执行业务任务
    result = agent.run("张三目前在参与什么项目？进度如何？")
