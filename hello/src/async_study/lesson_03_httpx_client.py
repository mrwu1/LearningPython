# async query function
import asyncio

import httpx


async def fetch_api(client: httpx.AsyncClient, query_param: str):
    print(f"Fetching API data for {query_param}...")
    response = await client.get(f"https://httpbin.org/get?tag={query_param}")
    print(response.status_code == 200)
    print(f"API data for {query_param} fetched!")
    return response.json()["args"]["tag"]


async def main():
    start_time = asyncio.get_event_loop().time()
    async with httpx.AsyncClient() as client:
        tasks = [
            fetch_api(client, param)
            for param in ["agent_alpha", "agent_beta", "agent_gamma"]
        ]
        results = await asyncio.gather(*tasks)
        end_time = asyncio.get_event_loop().time()
        print(f"Results: {results}")
        print(f"Total time: {end_time - start_time}")


if __name__ == "__main__":
    asyncio.run(main())
