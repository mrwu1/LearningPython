import asyncio


sem = asyncio.Semaphore(3)  # Limit to 3 concurrent requests


async def fetch_with_limit(sem: asyncio.Semaphore, task_name: str):
    # 核心：必须使用 async with sem 拿号排队！
    async with sem:
        print(f"🟢 Starting task: {task_name}")
        # 模拟耗时操作
        await asyncio.sleep(2)  # Simulate delay
        print(f"🔴  Task completed: {task_name},return t")
        return f"{task_name} 数据"


async def main():
    start_time = asyncio.get_event_loop().time()
    tasks = [fetch_with_limit(sem, f"Task {i}") for i in range(1, 7)]
    result = await asyncio.gather(*tasks)
    end_time = asyncio.get_event_loop().time()
    print(f"Total time: {end_time - start_time}")
    print(f"Results: {result}")


if __name__ == "__main__":
    asyncio.run(main())
