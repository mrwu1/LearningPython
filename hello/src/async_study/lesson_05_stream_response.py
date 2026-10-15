import asyncio

import httpx


async def fetch_stream_data():
    async with httpx.AsyncClient() as client:  # noqa: SIM117
        # 核心：流式请求是上下文管理器，必须用 async with client.stream(...) as response:
        async with client.stream("GET", "https://httpbin.org/stream/5") as response:
            print("🌊 开始接收流式数据推送...")
            # 异步遍历流式数据块
            async for chunk in response.aiter_text():
                clean_chunk = chunk.strip()
                if clean_chunk:
                    print(f"📥 收到数据块: {clean_chunk}")


async def main():
    await fetch_stream_data()


if __name__ == "__main__":
    asyncio.run(main())
