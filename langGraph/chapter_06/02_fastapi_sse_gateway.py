"""
================================================================================
【LangGraph 阶段六：全场景流式通信与生产网关】第 2 课：企业级 FastAPI SSE 流式网关与反向代理防缓冲
================================================================================
【核心学习目标】：
1. 掌握生产级 FastAPI + LangGraph SSE（Server-Sent Events）集成范式：
   - 使用 lifespan 在应用启动时完成单例图的预编译（单例模式，避免并发请求反复编译图）；
   - 将编译好的图挂载到 `app.state.graph` 供所有异步请求安全共享。
2. 掌握异步流式生成器 `graph.astream(...)`：
   - 监听 `custom`（业务步骤进度）、`messages`（逐字打字机）、`updates`（超步完成）三类事件；
   - 包装为符合 W3C 标准的 SSE 事件协议格式：`event: ...\ndata: ...\n\n`。
3. 掌握生产级网络防御与资源释放：
   - `await request.is_disconnected()`：客户端（浏览器/移动端）关闭标签页或断网时，立即中断生成，防止服务端协程孤儿空转浪费 Token；
   - `X-Accel-Buffering: no` 响应头：防止 Nginx / ALB 等反向代理层对流式数据进行缓冲拼包导致打字机失效。
================================================================================
"""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TypedDict, Annotated

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

from fastapi import FastAPI, Request
from langchain_core.messages import BaseMessage, HumanMessage, AIMessageChunk
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.graph import add_messages, StateGraph
from langgraph.types import StreamWriter
from loguru import logger
from pydantic import BaseModel, Field
from sse_starlette import EventSourceResponse


# ==============================================================================
# 第一步：定义状态契约与 HTTP 请求体
# ==============================================================================

# 图状态契约
class ServiceState(TypedDict):
    order_id: str
    messages: Annotated[list[BaseMessage], add_messages]
    logistics_status: str


# 客户端 HTTP POST 请求入参模型
class ChatStreamRequest(BaseModel):
    session_id: str = Field(..., description="用户唯一会话标识或 thread_id")
    order_id: str = Field(..., description="关联的目标外卖订单号")
    query: str = Field(..., description="用户发送的咨询文本")


# ==============================================================================
# 第二步：定义图计算节点
# ==============================================================================

async def order_lookup_node(state: ServiceState):
    """【节点 1：物流检索】：模拟异步从微服务或缓存中检索订单实时配送状态。"""
    await asyncio.sleep(0.3)  # 模拟网络 IO 耗时
    return {"logistics_status": "骑手已到达商家后厨，正在取餐装车。"}


async def llm_agent_node(state: ServiceState, writer: StreamWriter):
    """
    【节点 2：大模型思考与流式输出】：
    - 先通过 writer 发送进度事件；
    - 调用 DeepSeek 模型异步流式推理。
    """
    writer({"step": "LLM_REASONING", "detail": "DeepSeek-V3 正在基于最新物流数据推理回复..."})

    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.0,
        streaming=True  # 开启模型底层 Token 流式推送
    )

    prompt = [
        HumanMessage(content=(
            f"你是苍穹外卖智能助手。\n"
            f"当前物流状态: {state['logistics_status']}\n"
            f"顾客提问: '{state['messages'][-1].content}'\n"
            f"请以温暖客气的口吻，在2句话内给出令人安心的回复。"
        ))
    ]

    response = await llm.ainvoke(prompt)
    return {"messages": [response]}


# ==============================================================================
# 第三步：构建并编译图引擎
# ==============================================================================
def build_compiled_graph():
    builder = StateGraph(ServiceState)
    builder.add_node("lookup", order_lookup_node)
    builder.add_node("agent", llm_agent_node)

    builder.add_edge(START, "lookup")
    builder.add_edge("lookup", "agent")
    builder.add_edge("agent", END)

    return builder.compile()


# ==============================================================================
# 第四步：FastAPI 应用生命周期管理（单例模式）
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    【企业生产黄金规范】：
    图的编译（compile）包含拓扑校验与预热，绝不能在每个用户请求里重复执行！
    在应用启动事件（Lifespan Startup）中只编译一次，存储在 app.state 中全局复用。
    """
    logger.info("⚡ [Lifespan 启动] 正在编译 LangGraph 全局单例引擎...")
    app.state.graph = build_compiled_graph()
    logger.info("✅ [Lifespan 启动] 单例图引擎编译完成，已就绪接收高并发流量。")
    yield
    logger.info("🛑 [Lifespan 停机] 网关正在清理连接与释放资源...")


app = FastAPI(title="苍穹外卖智能体 SSE 生产网关", lifespan=lifespan)


# ==============================================================================
# 第五步：SSE 流式核心路由端点（/api/v1/chat/stream）
# ==============================================================================
@app.post("/api/v1/chat/stream")
async def chat_stream_endpoint(payload: ChatStreamRequest, request: Request):
    # 从全局上下文中取出预编译好的图实例
    graph = request.app.state.graph
    session_config = {"configurable": {"thread_id": payload.session_id}}

    initial_input = {
        "order_id": payload.order_id,
        "messages": [HumanMessage(content=payload.query)],
        "logistics_status": ""
    }

    async def sse_event_generator():
        """异步事件生成器：将 LangGraph 复合流实时转化为 SSE 格式数据包。"""
        try:
            # 开启三通道并发流：custom（自定义进度）、messages（Token块）、updates（节点完成）
            async for mode, event in graph.astream(
                initial_input,
                stream_mode=["custom", "messages", "updates"],
                config=session_config
            ):
                # 【核心防御】：检测客户端是否主动挂断或关闭了浏览器网页
                if await request.is_disconnected():
                    logger.warning(f"客户端提前断开连接 (Session: {payload.session_id})，立即终止流生成以节约算力！")
                    break

                # 1. 自定义业务事件（推给前端进度指示器）
                if mode == "custom":
                    yield {
                        "event": "progress",
                        "data": json.dumps(event)
                    }

                # 2. 逐 Token 打字机事件
                elif mode == "messages":
                    chunk, metadata = event
                    if isinstance(chunk, AIMessageChunk) and chunk.content:
                        yield {
                            "event": "token",
                            "data": json.dumps({"content": chunk.content})
                        }

                # 3. 超步节点完成更新
                elif mode == "updates":
                    node_name = list(event.keys())[0]
                    yield {
                        "event": "node_complete",
                        "data": json.dumps({"node": node_name})
                    }

            # 4. 流式正常结束哨兵标记
            yield {
                "event": "done",
                "data": "[DONE]"
            }

        except Exception as e:
            logger.error(f"流式生成中途发生异常: {str(e)}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }

    # 【关键响应头配置】：
    # - Cache-Control: no-cache（禁用缓存）
    # - X-Accel-Buffering: no（核心！禁止 Nginx 反向代理层对流式数据进行 chunk 缓存拼包）
    return EventSourceResponse(
        sse_event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


# ==============================================================================
# 第六步：测试客户端模拟（验证真实 HTTP SSE 通信）
# ==============================================================================
async def run_client_simulation():
    """在后台启动临时 uvicorn 服务，并利用 httpx.AsyncClient 进行全真 SSE 消费测试。"""
    import httpx

    # 1. 后台拉起测试服务
    server_config = uvicorn.Config(app, host="127.0.0.1", port=8099, log_level="warning")
    server = uvicorn.Server(server_config)
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.8)  # 等待服务端口就绪

    print("\n" + "=" * 65)
    print("🌐 启动真实 HTTP SSE 客户端消费测试...")
    print("=" * 65)

    request_payload = {
        "session_id": "CUSTOMER_WEB_SESSION_777",
        "order_id": "SKY-ORDER-9912",
        "query": "你好，请问我的餐品快好了吗？"
    }

    # 2. 发起流式 HTTP 请求
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream(
            "POST",
            "http://127.0.0.1:8099/api/v1/chat/stream",
            json=request_payload
        ) as response:
            print(f"HTTP 响应状态码: {response.status_code}")
            print(f"响应 Content-Type: {response.headers.get('content-type')}\n")

            current_event = None
            async for line in response.aiter_lines():
                if not line:
                    continue
                if line.startswith("event: "):
                    current_event = line.replace("event: ", "").strip()
                elif line.startswith("data: "):
                    raw_data = line.replace("data: ", "").strip()
                    if raw_data == "[DONE]":
                        print("\n\n[SSE 结束哨兵 🏁] 整个流式通信正常结束。")
                        break

                    data_json = json.loads(raw_data)
                    if current_event == "progress":
                        print(f"[SSE 进度事件 ⏳] {data_json['step']}: {data_json['detail']}")
                    elif current_event == "token":
                        # 实时打印单字
                        print(data_json["content"], end="", flush=True)
                    elif current_event == "node_complete":
                        print(f"\n[SSE 节点完成 ✅] 节点 '{data_json['node']}' 执行完毕。")

    print("\n" + "=" * 65)
    print("🏁 测试顺利完成，正在关闭后台测试服务...")
    print("=" * 65)

    server.should_exit = True
    await server_task


if __name__ == "__main__":
    asyncio.run(run_client_simulation())
