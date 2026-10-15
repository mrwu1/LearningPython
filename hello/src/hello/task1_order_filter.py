from collections import Counter
from typing import Any, Literal

# 1.类型别名字典：定义允许的订单状态
OrderStatus = Literal["PENDING", "PAID", "DELIVERED", "CANCELED"]
# 2.模拟订单测试数据
mock_orders: list[dict[str, Any]] = [
    {
        "id": 1001,
        "amount": 45.0,
        "status": "DELIVERED",
        "items": ["可乐", "香辣鸡腿堡", "薯条"],
    },
    {"id": 1002, "amount": 20.0, "status": "DELIVERED", "items": ["可乐", "原味圣代"]},
    {"id": 1003, "amount": 58.5, "status": "PAID", "items": ["烤鸡", "啤酒"]},
    {
        "id": 1004,
        "amount": 88.0,
        "status": "DELIVERED",
        "items": ["香辣鸡腿堡", "烤鸡", "可乐", "薯条"],
    },
    {"id": 1005, "amount": 15.0, "status": "CANCELLED", "items": ["可乐"]},
    {
        "id": 1006,
        "amount": 32.0,
        "status": "DELIVERED",
        "items": ["香辣鸡腿堡", "可乐"],
    },
]


# 定义函数 - 统计菜品频次
def analyze_delivered_dishes(
    orders: list[dict[str, Any]], min_amount: float = 30.0
) -> dict[str, int]:
    # 1. 筛选条件：订单状态必须为 "DELIVERED" 且 金额 (amount) >= min_amount；
    # 2. 提取数据：提取出所有符合条件订单里的菜品 (items)；
    # 3. 频次聚合：使用 Counter 统计每个菜品出现的总次数；
    # 4. 返回结果：将 Counter 对象转为普通字典 dict 返回。
    o1 = [
        order
        for order in orders
        if order["status"] == "DELIVERED" and order["amount"] >= min_amount
    ]
    dishes = [dishs for order in o1 for dishs in order["items"]]
    print(dishes)
    dishes_counter = Counter(dishes)
    print(dishes_counter)
    return dict(dishes_counter)


if __name__ == "__main__":
    result = analyze_delivered_dishes(mock_orders, min_amount=30.0)
    print("=== 达标订单菜品销售统计结果 ===")
    print(result)
