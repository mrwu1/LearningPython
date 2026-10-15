from typing import Literal

from pydantic import BaseModel, Field


class CloudAction(BaseModel):
    # 大模型只能从 "restart", "stop", "status" 中选一个，JSON Schema 会自动生成 "enum": [...]
    action: Literal["restart", "stop", "status"] = Field(..., description="操作指令")


tt = {
    "properties": {
        "action": {
            "description": "操作指令",
            "enum": ["restart", "stop", "status"],
            "title": "Action",
            "type": "string",
        }
    },
    "required": ["action"],
    "title": "CloudAction",
    "type": "object",
}
schema = CloudAction.model_json_schema()
print(schema)
