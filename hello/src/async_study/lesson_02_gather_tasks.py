import asyncio


async def fetch_weather(city: str):
    print(f"Fetching weather for {city}...")
    await asyncio.sleep(1)  # Simulate network delay
    print(f"Weather for {city} fetched!")
    return f"Weather data for {city}"


async def fetch_stock():
    print("Fetching stock data...")
    await asyncio.sleep(1.5)
    raise RuntimeError("Failed to fetch stock data")


async def fetch_news():
    print("Fetching news...")
    await asyncio.sleep(2)
    print("News fetched!")
    return "News data"


async def main():
    tasks = [fetch_weather("Beijing"), fetch_stock(), fetch_news()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            print(f"❌ {result}")
        else:
            print(f"✅ {result}")


if __name__ == "__main__":
    asyncio.run(main())
