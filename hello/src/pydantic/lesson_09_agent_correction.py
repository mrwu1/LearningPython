### 场景设定：

#   用户向订票助手 Agent 说：“帮我预订一张明天去北京的高铁票”。Agent 需要提取参数并调用订票工具。

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError


# 1. 定义工具参数契约模型
class TicketBookingArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    passenger_name: str = Field(..., description="乘客姓名")
    id_card: str = Field(
        ..., alias="idCard", pattern=r"^\d{17}[\dXx]$", description="身份证号"
    )
    origin: str = Field(..., description="出发地")
    destination: str = Field(..., description="目的地")
    seat_type: Literal["一等座", "二等座", "商务座"] = Field(
        ..., description="座位类型"
    )
    ticket_count: int | None = Field(default=1, ge=1, le=5, description="票数")


# 2. 模拟大模型输出函数（Round 1 犯错，Round 2 知错就改）
def mock_llm_response(round_num: int) -> str:
    if round_num == 1:
        # 第 1 轮：大模型生成了非法身份证（仅6位）以及非法的“特等座”
        return '{"passenger_name": "张三", "id_card": "110101", "origin": "上海", "destination": "北京", "seat_type": "特等座"}'
    if round_num == 2:
        # 第 2 轮：大模型根据反馈修正了数据
        return '{"passenger_name": "张三", "id_card": "110101199003072345", "origin": "上海", "destination": "北京", "seat_type": "二等座"}'
    return ""


# 2.9 定义异常格式化函数
def format_validation_errors(errors: list[dict]) -> list[str]:
    formatted = []
    for error in errors:
        path = " -> ".join(map(str, error["loc"]))
        msg = error.get("msg")
        val = error.get("input")
        formatted.append(f"❌ 路径 [{path}] | 原因: {msg} | 实际输入: {val}")
    return formatted


# 3. 编写生产级自愈循环函数
def execute_agent_with_self_correction(max_retries: int = 3):
    print("🚀 Agent 启动订票任务...")
    for attempt in range(1, max_retries + 1):
        print(f"\n--- [第 {attempt} 轮交互] ---")
        raw_json = mock_llm_response(attempt)
        print(f"🤖 大模型输出的参数: {raw_json}")

        try:
            result = TicketBookingArgs.model_validate_json(raw_json)
            print("\n🎉 校验成功！参数合法，正在执行订票系统底层调用...")
            print(f"📦 最终订票实体: {result}")
            return result
        except ValidationError as e:
            # 核心：提取错误并构造反馈 Prompt 喂回给大模型
            err_list = format_validation_errors(e.errors())
            print(f"⚠️ 第 {attempt} 轮校验失败，提炼出 {len(err_list)} 个错误:")
            for err in err_list:
                print(f"   {err}")

            prompt_feedback = "；".join(err_list)
            print(
                f"🔄 构造给大模型的纠错提示词: 「你的输出存在以下错误: {prompt_feedback}。请严格按照规则重新输出 JSON。」"
            )


# 运行测试
execute_agent_with_self_correction()
