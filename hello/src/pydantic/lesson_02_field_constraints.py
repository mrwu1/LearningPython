from pydantic import BaseModel, Field


class DeliveryOrder(BaseModel):
    order_id: str = Field(..., description="订单全局唯一标识")
    receiver_phone: str = Field(
        ..., pattern=r"^1[3-9]\d{9}$", description="收货人手机号码：11位，以1开头"
    )
    item_count: int = Field(..., ge=1, le=50, description="商品数量：1-50件")

    total_price: float = Field(..., gt=0, description="订单总金额：必须大于0")
    note: str | None = Field(default=None, max_length=30, description="订单备注：可选")


# test
d1 = DeliveryOrder(
    order_id="order_001",
    receiver_phone="13812345678",
    item_count="10",
    total_price="100.0",
)
print(d1)
raw_dict = {
    "order_id": "order_001",
    "receiver_phone": "13812345678",
    "item_count": "50",
    "total_price": "100.0",
}

d2 = DeliveryOrder.model_validate(raw_dict)
print(d2)
