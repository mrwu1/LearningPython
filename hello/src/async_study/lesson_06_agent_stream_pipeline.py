import asyncio
from asyncio import tasks

import httpx
from pydantic import BaseModel


class StreamChunkItem(BaseModel):
    id: int
    url: str


async def background_heartbeat(stop_event: asyncio.Event):
    while not stop_event.is_set():
        print("💓 [后台监控] Agent 主线程平稳运行中...", flush=True)
        await asyncio.sleep(0.5)


async def consume_llm_stream(stop_event: asyncio.Event) -> list[StreamChunkItem]:
    async with httpx.AsyncClient() as client:  # noqa: SIM117
        async with client.stream("GET", "https://httpbin.org/stream/5") as resp:
            collected_items: list[StreamChunkItem] = []
            async for chunk in resp.aiter_text():
                clean_chunk = chunk.strip()
                if clean_chunk:
                    print(f"📥 [接收数据] 收到 原始Chunk: {chunk}")
                    item = StreamChunkItem.model_validate_json(clean_chunk)
                    print(f"🖨️ [打字机输出] 解析到 Chunk ID: {item.id}", flush=True)
                    collected_items.append(item)
    # 核心：流式数据接收完毕，立即通知后台心跳退出！
    stop_event.set()
    return collected_items


async def main():
    stop_event = asyncio.Event()
    tasks = [background_heartbeat(stop_event), consume_llm_stream(stop_event)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            print(f"❌ {result}")
        else:
            print(f"✅ {result}")


if __name__ == "__main__":
    asyncio.run(main())
