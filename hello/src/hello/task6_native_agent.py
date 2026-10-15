import json

from openai import OpenAI
from pydantic import BaseModel, Field


# =====================================================================
# 1. 第一步：使用 Pydantic 定义工具的入参契约 (Schema)
# =====================================================================
class QueryDishInput(BaseModel):
    dish_id: int = Field(..., description="菜品编号，例如 101 或 102")


class CreateOrderInput(BaseModel):
    dish_id: int = Field(..., description="要购买的菜品编号")
    count: int = Field(..., ge=1, le=10, description="购买份数，必须在 1 到 10 之间")
    address: str = Field(..., min_length=5, description="详细收货地址")


# =====================================================================
# 2. 第二步：编写真正的本地业务函数 (真正执行代码的地方)
# =====================================================================
# 模拟外卖数据库
MOCK_DISH_DB = {
    101: {"name": "招牌香辣鸡腿堡", "price": 25.0, "stock": 10},
    102: {"name": "黄金脆薯条", "price": 12.0, "stock": 0},  # 缺货
}


def query_dish_inventory(dish_id: int) -> str:
    """根据菜品 ID 查询库存和单价"""
    print(f"\n⚙️  [本地执行工具] --> query_dish_inventory(dish_id={dish_id})")
    dish = MOCK_DISH_DB.get(dish_id)
    if not dish:
        return json.dumps(
            {"error": f"未找到编号为 {dish_id} 的菜品"}, ensure_ascii=False
        )

    result = {
        "dish_id": dish_id,
        "dish_name": dish["name"],
        "price": dish["price"],
        "stock": dish["stock"],
        "status": "充足" if dish["stock"] > 0 else "已售罄",
    }
    return json.dumps(result, ensure_ascii=False)


def create_takeout_order(dish_id: int, count: int, address: str) -> str:
    """执行外卖下单业务"""
    print(
        f"\n⚙️  [本地执行工具] --> create_takeout_order(dish_id={dish_id}, count={count}, address='{address}')"
    )
    dish = MOCK_DISH_DB.get(dish_id)
    if not dish or dish["stock"] < count:
        return json.dumps(
            {"status": "FAILED", "reason": "库存不足或菜品不存在"}, ensure_ascii=False
        )

    total_amount = dish["price"] * count
    result = {
        "status": "SUCCESS",
        "order_id": "ORD_20261013_998",
        "dish_name": dish["name"],
        "count": count,
        "total_amount": total_amount,
        "delivery_address": address,
        "message": "下单成功，骑手正在火速接单中！",
    }
    return json.dumps(result, ensure_ascii=False)


# 工具注册表：将大模型传回的函数名称字符串，精确路由到真正的 Python 函数
TOOL_REGISTRY: dict[str, Callable] = {
    "query_dish_inventory": query_dish_inventory,
    "create_takeout_order": create_takeout_order,
}

# =====================================================================
# 3. 第三步：组装标准工具元数据 (OpenAI Tools 协议规范)
# =====================================================================
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "query_dish_inventory",
            "description": "查询指定菜品的名称、单价与当前库存状态",
            "parameters": QueryDishInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_takeout_order",
            "description": "提交外卖订单，完成购买。下单前必须确保已经查询过库存且库存充足。",
            "parameters": CreateOrderInput.model_json_schema(),
        },
    },
]


# =====================================================================
# 4. 第四步：核心自主智能体运行时 (The Native ReAct Loop)
# =====================================================================
def run_agent_loop(
    user_query: str, max_turns: int = 5, model_name: str = "llama3.2:3b"
):
    """纯原生手写 Agent 决策与执行循环 (ReAct 状态机)

    核心步骤：
    1. 初始化 OpenAI SDK 客户端（连接本地 Ollama）；
    2. 维护 messages 会话上下文（状态）；
    3. 进入 while 决策循环：
       - 发送当前上下文 + 工具 Schema 给模型；
       - 模型决策：
         * 无 tool_calls: 说明任务完成，输出最终自然语言回答，结束！
         * 有 tool_calls: 解析参数，调用本地 Python 函数，构造 role='tool' 消息回传模型，继续循环！
    """
    # 1. 初始化客户端（连接本地 Ollama 服务，macOS 请务必使用 127.0.0.1 避开 IPv6 代理 503 陷阱）
    client = OpenAI(
        base_url="http://127.0.0.1:11434/v1",
        api_key="ollama",  # 本地运行无需真实 Key
    )

    # 2. 声明会话上下文状态（包含 System 提示词和用户的输入）
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个专业、严谨的外卖订餐智能助手。"
                "你可以使用提供的工具查询库存并在库存充足时下单。"
                "如果需要调用工具，请积极调用工具；"
                "当所有操作完成后，请用亲切、清晰的中文向用户总结最终结果。"
            ),
        },
        {"role": "user", "content": user_query},
    ]

    print("=" * 65)
    print(f"🤖 [Agent 启动] 收到用户指令: {user_query}")
    print("=" * 65)

    turn = 0
    while turn < max_turns:
        turn += 1
        print(f"\n🔄 [第 {turn} 轮思考与决策...]")

        # a. 向模型发送请求，同时携带上下文和工具定义
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=TOOLS_SCHEMA,
            temperature=0.1,  # 低温度，让模型在调工具时保持高度严谨
        )

        response_msg = response.choices[0].message

        # b. 将模型的输出原样追加到历史消息列表中（保留模型的思考轨迹）
        messages.append(response_msg)
        print(f"模型返回结果：{response}")

        # c. 判断模型是否需要调用工具
        if not response_msg.tool_calls:
            print("\n🎉 [模型任务完成，无需进一步调用工具] 最终回复如下：")
            print("-" * 65)
            print(response_msg.content)
            print("-" * 65)
            return response_msg.content

        # d. 模型返回了 tool_calls，依次解析并执行本地 Python 代码
        print(f"💡 [模型做出决策] 决定调用 {len(response_msg.tool_calls)} 个工具：")

        for tool_call in response_msg.tool_calls:
            tool_id = tool_call.id
            func_name = tool_call.function.name
            raw_args = tool_call.function.arguments

            print(f"  • 工具名称: {func_name}")
            print(f"  • 模型传入的原始参数字符串: {raw_args}")

            # 解析参数：将 JSON 字符串反序列化为 Python 字典
            try:
                args_dict = json.loads(raw_args)
            except json.JSONDecodeError as e:
                print(f"  ❌ 参数 JSON 解析失败: {e}")
                args_dict = {}

            # 从注册表中找到真实函数，并使用解包语法 (**args_dict) 执行
            if func_name in TOOL_REGISTRY:
                real_func = TOOL_REGISTRY[func_name]
                try:
                    tool_result_str = real_func(**args_dict)
                except Exception as e:
                    tool_result_str = json.dumps(
                        {"error": f"工具执行抛出异常: {str(e)}"}, ensure_ascii=False
                    )
            else:
                tool_result_str = json.dumps(
                    {"error": f"未知的工具名称: {func_name}"}, ensure_ascii=False
                )

            print(f"  • 本地执行输出: {tool_result_str}")

            # 【最关键协议】：必须将工具执行结果包装为 role: "tool"，并带上对应的 tool_call_id
            tool_message = {
                "role": "tool",
                "tool_call_id": tool_id,
                "content": tool_result_str,
            }
            messages.append(tool_message)

    print("\n⚠️ [警告] 达到最大决策轮次上限，强制退出循环！")
    return "已达最大循环轮次。"


if __name__ == "__main__":
    # 测试场景：用户意图明确，需要先查库存，库存充足后自动下单
    prompt = "帮我查一下 101 号菜品还有没有库存，如果有的话帮我订 2 份送去中关村南大街1号院。"
    run_agent_loop(prompt, max_turns=5, model_name="llama3.2:3b")
