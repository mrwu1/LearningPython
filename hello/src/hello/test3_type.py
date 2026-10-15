from typing import Any, Literal


name: str = "Alice"
num: int = 100
price: float = 19.90
is_open: bool = True

# 联合类型
# 数字，字符串
a: int | str = 100

# 可选类型
b: str | None = None

# 字面量枚举
StatusType = Literal["pending", "finished", "fail"]
current_status: StatusType = "pending"

# 复合容器类型
dish_names: list[str] = ["Pizza", "Burger", "Puzzle", "Drink"]

order_info: dict[str, Any] = {"id": 1, "status": "paid"}
