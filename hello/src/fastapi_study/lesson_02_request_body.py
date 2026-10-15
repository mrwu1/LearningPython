from fastapi import FastAPI
from pydantic import BaseModel, Field


class TaskCreateRequest(BaseModel):
    task_id:str = Field(...,description="任务全局唯一id")
    user_query:str = Field(...,min_length=3,description="用户发给 Agent 的任务指令")
    max_steps:int = Field(default=5,ge=1,le=10,description="最大迭代步数限制")
    temperature:float= Field(default=0.7,ge=0.0,le=1.0,description="模型采样温度")

class TaskResponse(BaseModel):
    task_id:str
    status:str
    estimated_duration_sec:int
    message:str

app = FastAPI(title="course_02")

@app.post("/tasks/execute",response_model=TaskResponse)
async def execute(params:TaskCreateRequest):
    return {
        "task_id":params.task_id,
        "status":"accept",
        "estimated_duration_sec":20,
        "message":"the work has been done!"
    }

@app.get("/tasks")
async def get_tasks(limit:int=3,status:str="all"):
    # 返回一个包含模拟任务列表的 JSON 字典
    return {
        "what":"i do not know."
    }

if __name__=="__main__":
    import uvicorn
    uvicorn.run("lesson_02_request_body:app",host="127.0.0.1",port=8000,reload=True)