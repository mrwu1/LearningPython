import asyncio
import json
from typing import AsyncGenerator

from fastapi import FastAPI
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse


class ChatRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        description="用户输入提问",
        examples=["请推荐两道招牌菜"],
    )
    user_id:int = Field(default=1001,description="用户id")

class ChatResponse(BaseModel):
    reply: str
    status: str = "SUCCESS"

async def fake_llm_stream(prompt: str)->AsyncGenerator[str,None]:
    """
           异步生成器：模拟大模型思考后，逐 Token 产出 SSE 格式的文本块

           SSE 标准格式要求：
           每条消息以 'data: 内容\n\n' 结尾！
    """
    chunks = [
        f"收到您的咨询：'{prompt}'。\n",
        "我是外卖智能管家。\n",
        "今日热销推荐：\n",
        "1. 招牌香辣鸡腿堡 (¥25.0) - 库存充足\n",
        "2. 黄金脆薯条 (¥12.0) - 口感酥脆\n",
        "如需订购，请告诉我您的收货地址！"
    ]

    for chunk in chunks:
        await asyncio.sleep(0.4)
        payload = json.dumps({"token":chunk},ensure_ascii=False)
        yield f"data: {payload} \n\n"
    # end push
    yield "data: [done] \n\n"

app = FastAPI(title="sky takeout agent service", version="1.0")

# define a few routers
 # 接口一：传统同步/一次性响应
@app.post("/api/takeout/chat",response_model=ChatResponse)
async def defnormal_char(request: ChatRequest):
    """普通问答接口（一次性返回完整答案）"""
    print(f"收到普通请求: 用户 {request.user_id}, 内容: {request.prompt}")
    return ChatResponse(
        reply=f"您好！已收到关于 '{request.prompt}' 的查询，当前外卖系统运行正常。"
    )

# 接口二：流式打字机响应 (核心)
@app.post("/api/takeout/chat/stream")
async def stream_chat(request: ChatRequest):
    return StreamingResponse(
        fake_llm_stream(request.prompt),
        media_type="text/event-stream"
    )

if __name__ =="__main__":
    import uvicorn
    uvicorn.run("task7_fastapi_server:app", host="127.0.0.1", port=8000, reload=True)