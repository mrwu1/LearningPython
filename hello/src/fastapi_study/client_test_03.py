import asyncio
import time
import httpx
import sys
from pathlib import Path

# 确保父级目录位于 sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from src.fastapi_study.lesson_03_streaming_sse import app
except ModuleNotFoundError:
    from lesson_03_streaming_sse import app


async def main():
    print("=" * 60)
    print("🚀 启动 FastAPI SSE 流式接收客户端演示")
    print("=" * 60)

    # 使用 ASGITransport 直接在内存中与 app 通信，无需开启独立端口也可极速测试流式！
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        # 1. 测试打字机文本流
        print("\n[演示 1] 请求纯文本流式打字机: GET /stream/raw-text ...")
        start = time.perf_counter()
        async with client.stream("GET", "/stream/raw-text?prompt=深入学习Python异步") as resp:
            async for chunk in resp.aiter_lines():
                if chunk.strip():  # 过滤空行
                    print(f"[{time.perf_counter() - start:.2f}s] 接收到 -> {chunk}")

        # 2. 测试 Agent 思考轨迹 JSON 流
        print("\n" + "=" * 60)
        print("[演示 2] 请求 Agent 结构化步骤流: POST /stream/agent-steps ...")
        start = time.perf_counter()
        payload = {"query": "排查生产环境订单超时熔断问题"}
        async with client.stream("POST", "/stream/agent-steps", json=payload) as resp:
            async for chunk in resp.aiter_lines():
                if chunk.strip():
                    print(f"[{time.perf_counter() - start:.2f}s] 接收到 -> {chunk}")

if __name__ == "__main__":
    asyncio.run(main())
