from typing import Generic, TypeVar

from pydantic import BaseModel, Field


# 商品详情
class ItemDetail(BaseModel):
    sku_id: str
    name: str
    price: float
    count: int = Field(..., ge=0)


# 订单详情
class OrderInfo(BaseModel):
    order_no: str
    customer_name: str
    items: list[ItemDetail]


# 响应模型
T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    code: int = Field(default=0)
    msg: str = Field(default="ok")
    data: T | None = None


raw_api_data = {
    "code": 0,
    "msg": "query success",
    "data": {
        "order_no": "ORD_20261009_001",
        "customer_name": "王五",
        "items": [
            {"sku_id": "SKU_01", "name": "机械键盘", "price": "299.0", "count": "1"},
            {"sku_id": "SKU_02", "name": "静音鼠标", "price": 99.0, "count": 2},
        ],
    },
}

# result = Result[OrderInfo](**raw_api_data)
result = Result[OrderInfo].model_validate(raw_api_data)
print(result)

print(result.data.customer_name)

print(type(result.data.items[0]))  # <class '__main__.ItemDetail'>

print("---------------")

test = """
{
    "code": 0,
    "msg": "query success",
    "data": {
        "order_no": "ORD_20261009_001",
        "customer_name": "王五",
        "items": [
            {"sku_id": "SKU_01", "name": "机械键盘", "price": "299.0", "count": "1"},
            {"sku_id": "SKU_02", "name": "静音鼠标", "price": 99.0, "count": 2}
        ]
    }
}
"""
result1 = Result[OrderInfo].model_validate_json(test)
print(result1)
