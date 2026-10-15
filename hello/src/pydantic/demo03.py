#   在第 1 课中，我们仅仅通过类型（如 int, str）约束数据。但在真实业务中，类型对齐是远远不够的：
#   • 年龄必须在 0 ~ 150 之间；
#   • 手机号必须符合特定正则；
#   • 大模型（LLM）调用工具时，它怎么知道这个参数是干嘛的？
#   这就是 Field(...) 的舞台！

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    # 数值约束范围
    quantity: int = Field(..., ge=1, le=100, description="购买数量，1到100件")
    # 字符串长度，与正则约束
    phone: str = Field(
        ..., pattern=r"^1[3-9]\d{9}$", description="手机号码：11位，以1开头"
    )
    # 选填字段默认值
    remark: str = Field(default="", max_length=100, description="商品备注：可选")

    # default_factory：当前时间戳、全新的唯一列表或 UUID
    # -- 每次新建对象时，调用 uuid4 生成新 ID，而不是所有对象共享同一个 uuid
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    create_at: datetime = Field(default_factory=datetime.now)


# test
o1 = OrderItem(quantity=5, phone="13812345678", remark="测试订单")
print(o1)
