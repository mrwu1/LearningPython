import asyncio
import time
import httpx
import sys
from pathlib import Path

# 确保项目根路径进入 sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from src.fastapi_study.lesson_04_agent_web_service import app
except ModuleNotFoundError:
    from lesson_04_agent_web_service import app


async def main():
    print("=" * 70)
    print("🤖 工业级流式 Agent Web 微服务 —— 全链路联调测试客户端")
    print("=" * 70)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

        # 1. 测试健康检查
        print("\n[1] 正在请求服务健康状态: GET /health ...")
        resp_h = await client.get("/health")
        print(f"👉 响应状态: {resp_h.status_code}, 内容: {resp_h.json()}")

        # 2. 测试获取工具列表与 Schema
        print("\n[2] 正在请求 Agent 工具元数据: GET /api/v1/agent/tools ...")
        resp_t = await client.get("/api/v1/agent/tools")
        print(f"👉 响应状态: {resp_t.status_code}")
        print(f"👉 注册工具总数: {resp_t.json().get('count')}")
        for t in resp_t.json().get("tools", []):
            print(f"   • 工具名: {t['name']} ｜ 描述: {t['description']}")

        # 3. 测试核心流式对话与 Agent 状态机推流
        print("\n" + "=" * 70)
        user_query = "查询张三当前负责的项目和最新研发进度"
        print(f"[3] 🚀 向 Agent 发起流式任务: '{user_query}' ...")
        print("=" * 70)

        start = time.perf_counter()
        async with client.stream(
            "POST",
            "/api/v1/agent/chat",
            json={"query": user_query}
        ) as resp:
            print(f"👉 连接已建立，HTTP 状态码: {resp.status_code}, Content-Type: {resp.headers.get('content-type')}\n")
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                elapsed = time.perf_counter() - start
                # 打印接收到的原生 SSE 数据帧
                print(f"[{elapsed:5.2f}s] {line}")

        print("\n" + "=" * 70)
        print("✅ 流式交互顺利完成，状态机全链路闭环！")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
