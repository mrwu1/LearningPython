from fastapi import FastAPI
from pydantic import BaseModel, Field
from sentry_sdk.integrations import fastapi

app = FastAPI(title="course_01")

class AgentTask(BaseModel):
    prompt:str = Field(...,min_length=1,description="用户输入指令")
    temperature:float = Field(default=0.7,ge=0.0,le=1.0)

@app.post("/task/{task_id")
async def create_task(
        task_id:str,
        task:AgentTask,
        user_token:str = 'default_token'
):
    # 当执行流进入此函数时，task 已经由 Pydantic 完成了反序列化与字段合法性校验！
    return {"id": task_id, "prompt": task.prompt, "token": user_token}

# 此外，还可以通过 response_model=... 指定出参模型：

@app.post("/task/execute",response_model=AgentTask)
async def execute(task:AgentTask)->AgentTask:
    return {
        "prompt":'1',
        "temperature":0.3
    }