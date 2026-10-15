from pydantic import BaseModel


class ToolRegistry:
    def __init__(self):
        # 内存路由表：存储 tool_name 与 (函数, 参数模型, 描述) 的映射
        self.tools = {}

    def register(self, name: str, description: str, args_model: type[BaseModel]):
        """装饰器：注册一个工具到路由表"""

        def decrator(func):
            self._tools[name] = {
                "func": func,
                "args_model": args_model,
                "description": description,
            }
            return func

        return decrator

    def get_tools_schema(self) -> list[dict]:
        """【一键导出】将所有注册的工具，自动转化为 OpenAI 标准的 tools 数组"""
        schemas = []
        for name, info in self._tools.items():
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": info["description"],
                        # 🎯 核心联动：直接调用 Pydantic V2 导出的 JSON Schema！
                        "parameters": info["args_model"].model_json_schema(),
                    },
                }
            )
        return schemas

    def execute(self, name: str, arguments_json: str):
        """【动态分发】根据名字查表，使用 Pydantic 校验并执行函数"""
        if name not in self._tools:
            raise ValueError(f"Tool not found: {name}")
        tool_info = self._tools[name]
        # 🎯 核心联动：用 Pydantic 把大模型返回的原始 JSON 字符串直接转为强类型对象！
        args_obj = tool_info["args_model"].model_validate_json(arguments_json)

        # 调用真实函数并返回结果字符串
        return str(tool_info["func"](args_obj))
