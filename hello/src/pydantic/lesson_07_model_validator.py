# 开发一个酒店房间预订模型（HotelBooking），
# 需要校验入住/离店日期关系，并自动派生计算“入住天数”与“预订总价”。

from datetime import date

from pydantic import BaseModel, Field, computed_field, model_validator


class HotelBooking(BaseModel):
    guest_name: str = Field(..., alias="guestName")
    room_price: float = Field(..., alias="roomPrice")
    check_in_date: date = Field(..., alias="checkInDate")
    check_out_date: date = Field(..., alias="checkOutDate")

    # 跨字段联合校验，日期大小
    @model_validator(mode="after")
    def validate_dates(self):
        if self.check_out_date <= self.check_in_date:
            raise ValueError("离店日期必须晚于入住日期")
        return self

    # 计算属性：必须显式标注返回值类型（如 -> int, -> float）
    @computed_field
    def cal_days(self) -> int:
        return (self.check_out_date - self.check_in_date).days

    @computed_field
    def cal_total_price(self) -> float:
        return round(self.cal_days * self.room_price, 2)


# 测试 1：正常预订（注意：支持前端直接传字符串日期 "2026-09-01"）
print("=== 测试 1：合法预订与自动计算 ===")
frontend = {
    "guestName": "John Doe",
    "roomPrice": 100.0,
    "checkInDate": "2026-09-01",
    "checkOutDate": "2026-09-05",
}
r = HotelBooking.model_validate(frontend)
print("解析出的对象:", r)
print(f"入住天数 (cal_days): {r.cal_days}")
print(f"总价格 (cal_total_price): {r.cal_total_price}")

# 重点观察：model_dump() 是否自动将计算属性导出为字典字段！
print("\n导出的字典 (model_dump):")
print(r.model_dump())

# 测试 2：离店早于入住（异常拦截）
print("\n=== 测试 2：日期颠倒拦截 ===")
bad_frontend = {
    "guestName": "Alice",
    "roomPrice": 100.0,
    "checkInDate": "2026-09-05",
    "checkOutDate": "2026-09-01",
}
try:
    HotelBooking.model_validate(bad_frontend)
except Exception as e:
    print("成功拦截日期倒挂！错误信息:")
    print(e)

