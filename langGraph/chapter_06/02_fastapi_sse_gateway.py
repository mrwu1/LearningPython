import asyncio
import os
from contextlib import asynccontextmanager
from typing import TypedDict, Annotated

import uvicorn
from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, Request
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.types import StreamWriter
from loguru import logger
from sse_starlette import EventSourceResponse
import json

load_dotenv(find_dotenv())
from langchain_core.messages import BaseMessage, HumanMessage, AIMessageChunk
from langgraph.graph import add_messages, StateGraph
from pydantic import BaseModel, Field


class ServiceState(TypedDict):
    order_id: str
    messages: Annotated[list[BaseMessage], add_messages]
    logistics_status: str


class ChatStreamRequest(BaseModel):
    session_id: str = Field(..., description="Unique user session or thread identifier")
    order_id: str = Field(..., description="Target takeout order ID")
    query: str = Field(..., description="User query message")

async def order_lookup_node(state:ServiceState):
    await asyncio.sleep(0.3)
    return {"logistics_status":"Courier arrived at restaurant, picking up food."}

async def  llm_agent_node(state:ServiceState,writer:StreamWriter):
    writer({"step": "LLM_REASONING", "detail": "DeepSeek-V3 is generating response..."})
    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.0,
        streaming=True
    )

    prompt = [
        HumanMessage(content=(
            f"You are Sky Takeout Assistant. "
            f"Order Status: {state['logistics_status']}. "
            f"Customer says: '{state['messages'][-1].content}'. "
            f"Give a friendly, reassuring reply in 2 sentences."
        ))
    ]

    # Model invocation generates streaming tokens caught by 'messages' stream_mode
    response = await llm.ainvoke(prompt)
    return {"messages": [response]}


def build_compiled_graph():
    builder = StateGraph(ServiceState)
    builder.add_node("lookup", order_lookup_node)
    builder.add_node("agent", llm_agent_node)

    builder.add_edge(START, "lookup")
    builder.add_edge("lookup", "agent")
    builder.add_edge("agent", END)

    return builder.compile()

@asynccontextmanager
async def lifespan(app: FastAPI):
        """
        Production Rule: Compile Graph ONCE during startup.
        Store compiled instance in app.state for concurrent sharing.
        """
        logger.info("⚡ [Lifespan Startup] Compiling LangGraph singleton engine...")
        app.state.graph = build_compiled_graph() #⚠️⚠️⚠️
        logger.info("✅ [Lifespan Startup] Graph compiled and ready for concurrent traffic.")
        yield
        logger.info("🛑 [Lifespan Shutdown] Cleaning up gateway resources...")

app = FastAPI(title="Sky Takeout Agent Gateway", lifespan=lifespan)


@app.post("/api/v1/chat/stream")
async def  chat_stream_endpoint(payload: ChatStreamRequest, request: Request):
    graph = request.app.state.graph
    session_config = {"configurable": {"thread_id": payload.session_id}}

    initial_input = {
        "order_id": payload.order_id,
        "messages": [HumanMessage(content=payload.query)],
        "logistics_status": ""
    }

    async def sse_event_generator():
        try:
            # Multi-mode composite async streaming
            async for mode, event in graph.astream(
                    initial_input,
                    stream_mode=["custom", "messages", "updates"],
                    config=session_config
            ):
                # Critical Defense: Detect if browser tab closed or user canceled
                if await request.is_disconnected():
                    logger.warning(f"Client disconnected for session {payload.session_id}. Aborting stream.")
                    break

                    # 1. Custom Business Progress Events (StreamWriter)
                if mode == "custom":
                    yield {
                        "event": "progress",
                        "data": json.dumps(event)
                    }

                    # 2. Token-by-Token Streaming (Typewriter Effect)
                elif mode == "messages":
                    chunk, metadata = event
                    if isinstance(chunk, AIMessageChunk) and chunk.content:
                        yield {
                            "event": "token",
                            "data": json.dumps({"content": chunk.content})
                        }

                        # 3. Superstep Node Completion
                elif mode == "updates":
                    node_name = list(event.keys())[0]
                    yield {
                        "event": "node_complete",
                        "data": json.dumps({"node": node_name})
                    }

                    # 4. Stream Termination Sentinel
            yield {
                "event": "done",
                "data": "[DONE]"
            }

        except Exception as e:
            logger.error(f"Error during stream generation: {str(e)}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }

            # Return standard SSE response with headers preventing reverse-proxy buffering

    return EventSourceResponse(
        sse_event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Prevents Nginx from buffering stream chunks!
        }
    )
# test
async def run_client_simulation():
        """Runs a temporary in-memory server and tests it with a real HTTP client."""
        import httpx

        # 1. Launch FastAPI server in background
        server_config = uvicorn.Config(app, host="127.0.0.1", port=8099, log_level="warning")
        server = uvicorn.Server(server_config)
        server_task = asyncio.create_task(server.serve())
        await asyncio.sleep(
            0.8)  # Wait for server boot

        print("\n" + "=" * 65)
        print(" 🌐 LIVE FASTAPI SSE HTTP CLIENT TEST")
        print("=" * 65)

        request_payload = {
            "session_id": "CUSTOMER_WEB_SESSION_777",
            "order_id": "SKY-ORDER-9912",
            "query": "Is my food almost ready?"
        }

        # 2. Consume SSE using httpx AsyncClient streaming
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                    "POST",
                    "http://127.0.0.1:8099/api/v1/chat/stream",
                    json=request_payload
            ) as response:
                print(f"HTTP Status: {response.status_code}")
                print(f"Content-Type: {response.headers.get('content-type')}\n")

                current_event = None
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("event: "):
                        current_event = line.replace("event: ", "").strip()
                    elif line.startswith("data: "):
                        raw_data = line.replace("data: ", "").strip()
                        if raw_data == "[DONE]":
                            print("\n\n[SSE SENTINEL] 🏁 Stream complete.")
                            break

                        data_json = json.loads(raw_data)
                        if current_event == "progress":
                            print(f"[SSE: Progress] ⏳ {data_json['step']}: {data_json['detail']}")
                        elif current_event == "token":
                            print(data_json["content"], end="", flush=True)
                        elif current_event == "node_complete":
                            print(f"\n[SSE: Node Done] ✅ Node '{data_json['node']}' completed.")

        print("\n" + "=" * 65)
        print(" 🏁 TEST FINISHED - SHUTTING DOWN SERVER")
        print("=" * 65)

        # 3. Clean up server task
        server.should_exit = True
        await server_task

if __name__ == "__main__":
        asyncio.run(run_client_simulation())