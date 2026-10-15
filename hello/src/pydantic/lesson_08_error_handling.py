from operator import le

from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    item_name: str
    price: float = Field(..., ge=0)
    quantity: int = Field(..., ge=1, le=10)


class OrderSubmit(BaseModel):
    customer_phone: str = Field(..., pattern=r"^1[3-9]\d{9}$")
    items: list[OrderItem]


ff = {
    "type": "greater_than",  # 机器可读的错误类型编码
    "loc": ("items", 1, "price"),  # 🎯【核心灵魂】出错字段的树状路径！
    "msg": "Input should be greater than 0",  # 人类可读的错误说明
    "input": -20.0,  # 引起错误的原始输入值
    "ctx": {"gt": 0.0},  # 上下文元数据（限制必须大于 0）
}


# 编写错误解析函数（提取全路径 loc，而不只是首个元素）
def format_validation_errors(errors):
    formatted = []
    for error in errors:
        # error['loc'] 是一个完整元组，如 ('items', 1, 'price')
        path = " -> ".join(map(str, error["loc"]))
        # 把 loc 里面每一项全部转成字符串：为什么要转？因为里面有数字，不能直接和字符串 join 拼接
        msg = error.get("msg")
        val = error.get("input")
        formatted.append(f"❌ 路径 [{path}] | 原因: {msg} | 实际输入: {val}")
    return formatted


# test
bad_order_data = {
    "customer_phone": "12345",  # 错误 1：手机号格式错误
    "items": [
        {"item_name": "键盘", "price": 199.0, "quantity": 1},
        {"item_name": "鼠标", "price": -50.0, "quantity": 2},  # 错误 2：价格为负数
        {"item_name": "显示器", "price": 999.0, "quantity": 99},  # 错误 3：数量超过10
    ],
}
# core‼️
try:
    OrderSubmit.model_validate(bad_order_data)
except Exception as e:
    print("验证失败！错误信息:")
    print(format_validation_errors(e.errors()))

# 验证失败！错误信息:
tt1 = [
    "❌ 路径 [customer_phone] | 原因: String should match pattern '^1[3-9]\\d{9}$' | 实际输入: 12345",
    "❌ 路径 [items -> 1 -> price] | 原因: Input should be greater than or equal to 0 | 实际输入: -50.0",
    "❌ 路径 [items -> 2 -> quantity] | 原因: Input should be less than or equal to 10 | 实际输入: 99",
]
