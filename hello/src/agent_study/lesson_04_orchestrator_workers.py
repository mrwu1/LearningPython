# “帮我规划一份三亚 3 日游攻略，需要包含：当地天气预报、特色海鲜餐厅、热门景点门票。”
# thought: get_weather, get seafood restraunt, popular landscape tickets
#  role: orchestrator, workers, synthesizer
#  api: asyncio.gather(**tasks)


import asyncio
import time


async def worker_weather(city: str) -> str:
    print(f"  [Worker-天气] 正在检索 {city} 天气...")
    await asyncio.sleep(1.5)  # 模拟网络 IO 延迟
    return f"{city} 未来 3 天晴空万里，气温 24~29°C，体感舒适。"


async def worker_restaurant(city: str) -> str:
    print(f"  [Worker-美食] 正在调研 {city} 海鲜特色餐厅...")
    await asyncio.sleep(1.5)
    return f"{city} 推荐餐厅：'爱潜水的鱼'海鲜大排档、'椰风海岸'特色海鲜加工坊。"


async def worker_attractions(city: str) -> str:
    print(f"  [Worker-景点] 正在查询 {city} 热门景点门票...")
    await asyncio.sleep(1.5)
    return f"{city} 推荐必游：亚龙湾热带天堂森林公园（门票 158 元）、蜈支洲岛（门票含船票 140 元）。"


async def orchestrator_travel_agent(user_query: str):
    start_time = time.perf_counter()
    print(f"🚀 [编排者] 收到用户指令: '{user_query}'")
    print("🧠 [编排者] 正在分析需求，动态拆解出 3 个并行子任务并分发给 Workers...")

    city = "三亚"
    # 构造并发任务列表
    tasks = [worker_weather(city), worker_restaurant(city), worker_attractions(city)]

    # 核心修复 1：列表解包是单星号 *tasks，双星号 ** 是用于字典的！
    weather, restaurant, attractions = await asyncio.gather(*tasks)

    # 核心修复 2：time.perf_counter 必须加括号调用函数 ()
    diff_time = time.perf_counter() - start_time

    print(f"\n⚡ [并行执行完毕] 3 个 Worker 任务全部就绪，总耗时: {diff_time:.2f} 秒！")

    # 合成者（Synthesizer）综合生成最终方案
    print("\n📝 [合成者] 综合 3 位 Worker 的成果，生成最终定制攻略:")
    print("=" * 60)
    print(f"🏖️ 【{city} 3 日游终极定制攻略】")
    print(f"• ☀️ 天气情况: {weather}")
    print(f"• 🦞 特色美食: {restaurant}")
    print(f"• 🎫 景点门票: {attractions}")
    print("=" * 60)


if __name__ == "__main__":
    # 核心修复 3：asyncio.run 需要传入协程调用对象，而不是函数名本身
    asyncio.run(orchestrator_travel_agent("帮我规划一份三亚 3 日游攻略"))

