from typing import Literal

from pydantic import BaseModel, Field


class SqlQueryArgs(BaseModel):
    database: Literal["user_db", "order_db", "analytics_db"] = Field(
        ..., description="数据库名称"
    )
    sql: str = Field(..., min_length=6, description="需要执行的只读 SELECT SQL 语句")
    max_rows: int | None = Field(
        default=None, ge=1, le=1000, description="最大返回行数"
    )
    timeout: float | None = Field(default=30.0, gt=0, description="查询超时时间（秒）")


# 导出 schema
schema = SqlQueryArgs.model_json_schema()
print(schema)
tt = {
    "properties": {
        "database": {
            "description": "数据库名称",
            "enum": ["user_db", "order_db", "analytics_db"],
            "title": "Database",
            "type": "string",
        },
        "sql": {
            "description": "需要执行的只读 SELECT SQL 语句",
            "minLength": 6,
            "title": "Sql",
            "type": "string",
        },
        "max_rows": {
            "anyOf": [
                {"maximum": 1000, "minimum": 1, "type": "integer"},
                {"type": "null"},
            ],
            "default": None,
            "description": "最大返回行数",
            "title": "Max Rows",
        },
        "timeout": {
            "anyOf": [{"exclusiveMinimum": 0, "type": "number"}, {"type": "null"}],
            "default": 30.0,
            "description": "查询超时时间（秒）",
            "title": "Timeout",
        },
    },
    "required": ["database", "sql"],  # 是否必填的标记
    "title": "SqlQueryArgs",
    "type": "object",
}
#  送入model的 data format
tools = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql_query",
            "description": "在指定业务数据库中执行只读 SQL 查询",
            "parameters": SqlQueryArgs.model_json_schema(),  # 👈 核心就在这里！
        },
    }
]
