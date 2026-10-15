import asyncio
import time


async def simulate_llm_call(model_name: str, delay: float):
    print(f"[{model_name}] 🚀 开始发起请求...")
    await asyncio.sleep(delay)  # 模拟 LLM 调用延迟
    print(f"[{model_name}] 📡 请求完成！耗时：{delay}秒")
    return f"{model_name} 的结果"


# 串行
async def run_serial():
    r1 = await simulate_llm_call("LLM-1", 1.0)
    r2 = await simulate_llm_call("LLM-2", 1.5)
    r3 = await simulate_llm_call("LLM-3", 2.0)


# concurrency
async def run_concurrent():
    tasks = [
        simulate_llm_call("LLM-1", 1.0),
        simulate_llm_call("LLM-2", 1.5),
        simulate_llm_call("LLM-3", 2.0),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # 增加异常处理
    for result in results:
        if isinstance(result, Exception):
            print(f"❌ {result}")
        else:
            print(f"✅ {result}")


# ❌❌❌
#  • 灾难现象：只要 task2 报错，gather 会立即把这个异常抛给你的外层代码！
#   • 严重后果：即使 task1 和 task3 已经成功拿到了数据，你的整个流程也会直接崩掉，那两个成功的珍贵结果统统丢失！


async def main():
    start_time = time.perf_counter()
    #     await run_serial()
    # 对比
    await run_concurrent()
    end_time = time.perf_counter()
    print(f"\n总耗时: {end_time - start_time:.2f} 秒")


if __name__ == "__main__":
    asyncio.run(main())
