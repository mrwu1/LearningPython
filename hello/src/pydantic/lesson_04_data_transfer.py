from pydantic import BaseModel, ConfigDict, Field


class TaskDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: int = Field(alias="taskId")
    task_title: str = Field(alias="taskTitle")
    assigned_to: str | None = Field(alias="assignedTo", default=None)
    is_completed: bool = Field(alias="isCompleted", default=False)


# 模拟前端传入的 JSON 字符串
frontend_json = '{"taskId": 101, "taskTitle": "编写 Agent 提示词"}'

# 反序列化
task_detail = TaskDetail.model_validate_json(frontend_json)
print("解析出的对象:", task_detail)

# 输出 1（默认导出为 Python 字典，自动转为蛇形命名）
print("\n--- 输出 1 (默认 model_dump) ---")
print(task_detail.model_dump())

# 输出 2（返回给前端：保留驼峰命名，且排除 None 字段）
print("\n--- 输出 2 (前端响应 by_alias & exclude_none) ---")
print(task_detail.model_dump_json(by_alias=True, exclude_none=True))

# 输出 3（PATCH 增量更新：只导出最初显式传入的字段） ‼️‼️
print("\n--- 输出 3 (增量更新 exclude_unset) ---")
print(task_detail.model_dump(exclude_unset=True))

schema = TaskDetail.model_json_schema()
print("\n--- JSON Schema ---")
print(schema)
