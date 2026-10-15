from pydantic import BaseModel, Field


class DeliveryConstraint(BaseModel):
    recipient_name: str = Field(
        ..., min_length=2, max_length=20, description="收件人姓名"
    )
    recipient_phone: str = Field(
        ..., pattern=r"^1[3-9]\d{9}$", description="收件人电话"
    )
    delivery_address: str = Field(..., min_length=5, description="配送地址")
    expected_delivery_hour: int = Field(..., ge=8, le=22, description="期望配送小时")
    notes: list[str] = Field(default=[], default_factory=list, description="备注")


def test_valid_data():
    print("=== 1. 测试合法数据解析与导出 ===")
    valid_payload = {
        "recipient_name": "张三",
        "recipient_phone": "13812345678",
        "delivery_address": "北京市海淀区中关村南大街1号院",
        "expected_delivery_hour": 18,
        "notes": ["多放辣", "放门口即可"],
    }
    delivery_constraint = DeliveryConstraint.model_validate(valid_payload)
    print(f"📦 解析后的配送约束: {delivery_constraint}")


test_valid_data()
