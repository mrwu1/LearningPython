import asyncio

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="stream_demo",version="0.0.1")

async def fake_llm_stream(prompt:str):
    tokens = ["思考中...", "找到相关数据...", "生成最终回答：", f"针对【{prompt}】，分析完毕！"]
    for token in tokens:
        await asyncio.sleep(0.5)  # 模拟大模型 token 生成延迟
        yield f"data:{token}\n\n" # 按照 SSE 规范格式组织并 yield 字符串
    yield "data: [DONE]\n\n"  # 按照业界规范发送结束标记

@app.get("/chat/stream")
async def chat_stream(prompt:str="hello"):
    return StreamingResponse(
        fake_llm_stream(prompt),
        media_type="text/event-stream"
    )



if __name__=="__main__":
    import uvicorn
    uvicorn.run("stream_03:app",host="127.0.0.1",port=8000,reload=True)