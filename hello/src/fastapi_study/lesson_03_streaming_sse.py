import asyncio
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

app = FastAPI(title="FastAPI 流式 SSE 演示与 Agent 步骤推送", version="1.0.0")


# ==============================================================================
# 接口 1：简单文本流式打字机 (GET) —— 从 stream_03.py 整合进来的纯文本流
# ==============================================================================

async def fake_llm_text_stream(prompt: str):
    """
    模拟大模型 Token 逐字吐出打字机效果
    """
    tokens = [
        "思考中...", 
        "找到相关数据...", 
        "生成回答：", 
        f"针对【{prompt}】，", 
        "系统已完成全链路检索与推演！"
    ]
    for token in tokens:
        await asyncio.sleep(0.3)  # 模拟大模型生成延迟
        # SSE 规范：每条消息必须以 "data: <内容>\n\n" 结尾
        yield f"data: {token}\n\n"
    
    # 行业通用规范：流结束标志
    yield "data: [DONE]\n\n"


@app.get("/stream/raw-text")
@app.get("/chat/stream")  # 同时兼容 stream_03 的原路径
async def chat_stream(prompt: str = "hello"):
    """
    流式打字机接口：返回 text/event-stream
    """
    return StreamingResponse(
        fake_llm_text_stream(prompt),
        media_type="text/event-stream"
    )


# ==============================================================================
# 接口 2：Agent 结构化思考流式接口 (POST) —— 结构化 JSON SSE 事件流
# ==============================================================================

class AgentStreamRequest(BaseModel):
    query: str = Field(..., min_length=1, description="用户发给 Agent 的任务指令")


class AgentStepEvent(BaseModel):
    step: int = Field(..., description="当前步骤序号")
    stage: str = Field(..., description="生命周期阶段：thought | tool_call | observation | answer")
    detail: str = Field(..., description="阶段详细内容")


async def do_agent_business_stream(query: str):
    """
    模拟 Agent 的思考/行动/观察/回答生命周期，逐步产出结构化 JSON
    """
    steps = [
        AgentStepEvent(step=1, stage="thought", detail=f"正在分析用户问题: '{query}'，拆解意图与依赖..."),
        AgentStepEvent(step=2, stage="tool_call", detail="命中工具库，正在调用: query_knowledge_base(query)"),
        AgentStepEvent(step=3, stage="observation", detail="知识库检索完成，命中 3 条核心规则与高频方案"),
        AgentStepEvent(step=4, stage="thought", detail="结合业务背景进行多视角综合推理..."),
        AgentStepEvent(step=5, stage="answer", detail=f"决策已生成：针对【{query}】，推荐采用方案 A 并配合熔断重试机制。"),
    ]

    for step_event in steps:
        await asyncio.sleep(0.4)  # 模拟每一步的耗时
        # 方式 1：利用 Pydantic 实例自带的 .model_dump_json() 方法
        json_str = step_event.model_dump_json()
        yield f"data: {json_str}\n\n"

    # 流式结束标记
    yield "data: [DONE]\n\n"


@app.post("/stream/agent-steps")
async def execute_agent_steps(request: AgentStreamRequest):
    """
    Agent 结构化步骤流式接口
    接收 JSON 请求体 (Pydantic 自动校验)，以 SSE 流式输出 Agent 执行轨迹
    """
    return StreamingResponse(
        do_agent_business_stream(request.query),
        media_type="text/event-stream"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("lesson_03_streaming_sse:app", host="127.0.0.1", port=8000, reload=True)
