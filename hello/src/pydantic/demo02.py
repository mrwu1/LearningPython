from pydantic import BaseModel


class Product(BaseModel):
    #     必填字段
    id: int
    name: str
    price: float
    #     选填字段
    description: str | None = None
    #     带有安全默认值的列表
    tags: list[str] = []
    #     boolean字段
    is_available: bool = True


# 实例化方式1:关键字参数传参（类似 Java 构造函数 / Lombok Builder）
p1 = Product(id=1, name="机械键盘", price=169.99)
# 实例化方式2: 通过字典动态解析（类似 Jackson ObjectMapper.readValue）
raw_dict = {"id": "1003", "name": "mouse", "price": 17.6, "is_available": "false"}
p2 = Product.model_validate(raw_dict)

# 测试结果
print(p1)
print(type(p2.id))  # <class 'int'> # 1002 (自动从 "1002" 转成 int)
print(p2)  ## False (自动从 "false" 识别成 bool)
