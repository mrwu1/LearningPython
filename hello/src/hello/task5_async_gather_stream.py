import asyncio
import time
import httpx


# =====================================================================
# 1. 模拟外部工具调用（异步协程函数）
# =====================================================================
async def fetch_tool_result(
    client: httpx.AsyncClient, tool_name: str, delay: float
) -> dict:
    """模拟调用一个外部接口或工具（如：查数据库、调用第三方微服务）

    【关键原理】：
    - async def: 声明这是一个协程函数（Coroutine）。调用它不会立即执行，而是返回一个协程对象。
    - await asyncio.sleep(delay):
        * 对标 Java: 千万不能用 time.sleep()！time.sleep() 是阻塞整个操作系统的线程；
        * asyncio.sleep() 是“非阻塞出让”。它通知事件循环：“我要等 delay 秒，你先去干别的任务吧”，
          这样单线程就可以并发调度成百上千个任务。
    """
    print(f"--> [启动任务] 开始请求工具: {tool_name} (预计耗时: {delay}s)")

    # 模拟网络 IO 等待（真正业务中这里通常是 await client.get("https://api...")）
    await asyncio.sleep(delay)

    print(f"<-- [完成任务] 工具返回成功: {tool_name} ✅")
    return {"tool": tool_name, "status": "SUCCESS", "elapsed": delay}


# =====================================================================
# 2. 核心实验一：Agent 多工具并发调度 (asyncio.gather)
# =====================================================================
async def test_concurrent_tool_calls():
    """【测试场景】：
    用户问：“帮我看看这单能不能用满减券，另外查下库存和配送费”
    Agent 需要同时调用 3 个独立工具：
      1. 库存查询 (耗时 1.0s)
      2. 优惠券查询 (耗时 1.5s)
      3. 配送距离测算 (耗时 2.0s)

    如果串行执行：总耗时 = 1.0 + 1.5 + 2.0 = 4.5s
    如果异步并发：总耗时 ≈ 最慢的任务耗时 (约 2.0s)
    """
    print("=" * 60)
    print("【实验 1】测试 Agent 多工具并发调用 (asyncio.gather)")
    print("=" * 60)

    start_time = time.perf_counter()

    # async with 类似于 Java 的 try-with-resources：
    # 自动管理 HTTP 连接池的创建与关闭，避免资源泄露。
    async with httpx.AsyncClient() as client:
        # 创建 3 个待执行的协程任务（注意：此时任务还未开始执行，只是创建了任务对象）
        tasks = [
            fetch_tool_result(client, "库存系统 (Stock Data)", 1.0),
            fetch_tool_result(client, "优惠券系统 (Coupon Data)", 1.5),
            fetch_tool_result(client, "配送系统 (Delivery Distance)", 2.0),
        ]

        # 【核心黑话：asyncio.gather(*tasks)】
        # - 对标 Java 的 CompletableFuture.allOf(future1, future2, future3)
        # - 符号 * 是参数解包：把列表 tasks 拆成独立的参数传进去
        # - 它会同时将 3 个任务推上事件循环并发推进，直到全部完成，并按传入顺序返回结果列表
        results = await asyncio.gather(*tasks)

    total_time = time.perf_counter() - start_time

    print("\n--- 并发调用结果汇总 ---")
    for r in results:
        print(f"  • 工具: {r['tool']:<26} 状态: {r['status']} 耗时: {r['elapsed']}s")

    print(f"\n全部工具调用结束！总耗时: {total_time:.2f} 秒")
    print("💡 结论：总耗时约 2.0s（取决于最慢的那个任务），证明 3 个工具是完全并行执行的！\n")


# =====================================================================
# 3. 核心实验二：异步流式生成与读取 (async for 与打字机效果)
# =====================================================================
async def test_streaming_stream():
    """【测试场景】：
    大模型生成回答不是一次性返回整段话，而是每个几毫秒吐一个 Token。
    我们需要用【异步生成器 (async def + yield)】和【async for】实现流式接收。
    """
    print("=" * 60)
    print("【实验 2】测试异步流式消费 (大模型流式打字机底层原理)")
    print("=" * 60)

    # 模拟大模型远程服务：这是一个异步生成器函数
    async def mock_remote_llm_stream():
        tokens = [
            "您好",
            "！",
            "系统",
            "已为您",
            "成功查询：",
            "\n1. 招牌",
            "香辣鸡腿堡",
            "（库存充足）",
            "\n2. 您的",
            "8折满减券",
            "可用",
            "\n3. 配送距离",
            "约 2.3 公里",
            "，预计 25 分钟",
            "送达。",
            "\n请问是否确认立即下单？",
        ]
        for token in tokens:
            # 模拟大模型生成每个词时的微小推理延迟 (约 80 毫秒)
            await asyncio.sleep(0.08)
            # yield: 产出当前 token 并冻结协程，把控制权还给调用方
            yield token

    print("大模型思考完毕，开始流式输出：\n")

    # 【核心黑话：async for】
    # - 普通 for 循环无法消费异步生成器
    # - async for 会在每一次迭代时 await 等待下一个产出的数据就绪
    # - end="" 避免每次打印自动换行
    # - flush=True 强制刷新操作系统标准输出缓冲区，实现平滑打字机视觉效果
    async for chunk in mock_remote_llm_stream():
        print(chunk, end="", flush=True)

    print("\n\n" + "=" * 60)
    print("【实验 2 结束】流式数据全部接收完毕！")
    print("=" * 60)


# =====================================================================
# 4. 程序主入口
# =====================================================================
async def main():
    # 依次演示：多工具并发调用 -> 异步流式输出
    await test_concurrent_tool_calls()
    await test_streaming_stream()


if __name__ == "__main__":
    # asyncio.run(main()) 是 Python 3.7+ 启动顶层事件循环的标准入口
    # 它负责：创建事件循环 -> 运行 main() 协程 -> 完成后优雅关闭循环与线程池
    asyncio.run(main())
