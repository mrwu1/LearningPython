# 为一个企业财务与 HR 智能体构建工具注册中心，注册以下两个业务工具：
#  1. 计算个人所得税工具 calculate_tax：
#       • 定义参数模型 TaxArgs(BaseModel)：
#           • income: 浮点数，必须大于 0，description="税前月收入金额（元）"
#       • 业务函数：
#           • 如果 args.income <= 5000，返回 "起征点以下，免税"；
#           • 否则返回 f"税前 {args.income} 元，需缴纳个税 {round((args.income - 5000) * 0.1, 2)} 元"。


#   2. 查询员工职级工具 get_employee_level：
#       • 定义参数模型 EmployeeArgs(BaseModel)：
#           • emp_id: 字符串，description="员工唯一工号，如 E001"
#       • 业务函数：
#           • 如果 args.emp_id == "E001" 返回 "P7 专家级技术顾问"；
#           • 否则返回 "P5 工程师"。

from pydantic import BaseModel, Field


class ToolFincialRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, name: str, description: str, args_model: type[BaseModel]):
        def decrator(func):
            self.tools[name] = {
                "func": func,
                "args_model": args_model,
                "description": description,
            }
            return func

        return decrator

    def get_tools_schema(self) -> list[dict]:
        schemas = []
        # 核心修复：遍历字典键值对必须加 .items()！
        for name, info in self.tools.items():
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

    def execute(self, name: str, arguments_json: str):
        if name not in self.tools:
            return f"错误：未找到名为 '{name}' 的工具"
        tool = self.tools[name]
        args_obj = tool["args_model"].model_validate_json(arguments_json)

        # 调用真实func 并返回结果字符串
        return str(tool["func"](args_obj))

    def __repr__(self):

        return f"demo(name={self.name!r})"

    def __str__(self):
        return f"The name of the instance is: {self.name}"

    # 可调用对象: 让实例本身也可以像函数一样直接加括号调用 obj()
    def __call__(self, query):
        return f"工具执行：{query}"


class TaxArgs(BaseModel):
    income: float = Field(..., gt=0, description="税前月收入金额（元）")


class EmployeeArgs(BaseModel):
    emp_id: str = Field(..., description="员工唯一工号，如 E001")


# create a instance:
register = ToolFincialRegistry()
res = register("LangGraph原理")
print(f"{res}")


# register two tools
@register.register(
    name="calculate_tax", description="计算个人所得税", args_model=TaxArgs
)
def calculate_tax_func(args: TaxArgs) -> str:
    if args.income <= 5000:
        return "起征点以下，免税"
    tax = round((args.income - 5000) * 0.1, 2)
    return f"税前 {args.income} 元，需缴纳个税 {tax} 元"


@register.register(
    name="get_employee_level", description="查询员工职级", args_model=EmployeeArgs
)
def get_employee_level_func(args: EmployeeArgs) -> str:
    if args.emp_id == "E001":
        return "P7 专家级技术顾问"
    return "P5 工程师"


# test
def main():
    tools_schema = register.get_tools_schema()
    print(f"tools_schema：{tools_schema}")

    print("-------------------------")

    res1 = register.execute("calculate_tax", '{"income": 120.0}')
    print("个税计算结果:", res1)

    res2 = register.execute("get_employee_level", '{"emp_id": "E001"}')
    print("员工职级结果:", res2)


if __name__ == "__main__":
    main()
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "calculate_tax",
            "description": "计算个人所得税",
            "parameters": {
                "properties": {
                    "income": {
                        "description": "税前月收入金额（元）",
                        "exclusiveMinimum": 0,
                        "title": "Income",
                        "type": "number",
                    }
                },
                "required": ["income"],
                "title": "TaxArgs",
                "type": "object",
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_employee_level",
            "description": "查询员工职级",
            "parameters": {
                "properties": {
                    "emp_id": {
                        "description": "员工唯一工号，如 E001",
                        "title": "Emp Id",
                        "type": "string",
                    }
                },
                "required": ["emp_id"],
                "title": "EmployeeArgs",
                "type": "object",
            },
        },
    },
]
