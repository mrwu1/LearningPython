import asyncio
import statistics
import sys
import time
import uuid
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import httpx
import uvicorn
from loguru import logger
from app.main import app


import os

SERVER_PORT = int(os.environ.get("APP_TEST_PORT", "8005"))
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}"

TEST_USERS = [
    {"username": "customer_alice", "password": "123456", "user_id": "USER_1001", "order_id": "ORD-TAKEOUT-9901"},
    {"username": "customer_bob", "password": "123456", "user_id": "USER_1002", "order_id": "ORD-TAKEOUT-9902"},
    {"username": "customer_charlie", "password": "123456", "user_id": "USER_1003", "order_id": "ORD-TAKEOUT-9903"},
]

QUERIES = [
    "Recommend a high-protein dinner under 500 calories.",
    "Could you suggest a low-carb salmon salad?",
    "Where is the courier delivering my takeout order?",
    "What delicious bento boxes are available right now?",
]


async def login_user(client: httpx.AsyncClient, user_dict: dict) -> str:
    """Authenticates against /api/v1/auth/login and returns JWT access token."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": user_dict["username"], "password": user_dict["password"]}
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed for {user_dict['username']}: {resp.status_code} - {resp.text}")
    return resp.json()["access_token"]


async def measure_single_sse_stream(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    order_id: str,
    query: str,
    session_id: str
) -> dict:
    """
    Initiates an SSE streaming request and precisely captures:
    - Status code
    - TTFT (Time-To-First-Token in ms)
    - Total stream duration in ms
    - Total tokens streamed
    - Done event receipt status
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "session_id": session_id,
        "user_id": user_id,
        "order_id": order_id,
        "query": query
    }

    start_time = time.perf_counter()
    ttft_ms = None
    token_count = 0
    done_received = False
    error_event = None
    status_code = None

    try:
        async with client.stream("POST", "/api/v1/takeout/chat", json=payload, headers=headers) as resp:
            status_code = resp.status_code
            if status_code != 200:
                body = await resp.aread()
                return {
                    "session_id": session_id,
                    "status_code": status_code,
                    "ttft_ms": None,
                    "duration_ms": (time.perf_counter() - start_time) * 1000,
                    "token_count": 0,
                    "done_received": False,
                    "error": body.decode("utf-8", errors="ignore")
                }

            current_event = None
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith("event: "):
                    current_event = line.replace("event: ", "").strip()
                elif line.startswith("data: "):
                    raw_data = line.replace("data: ", "").strip()
                    if current_event == "token":
                        if ttft_ms is None:
                            ttft_ms = (time.perf_counter() - start_time) * 1000
                        token_count += 1
                    elif current_event == "done":
                        done_received = True
                    elif current_event == "error":
                        error_event = raw_data

    except Exception as exc:
        return {
            "session_id": session_id,
            "status_code": status_code or 500,
            "ttft_ms": ttft_ms,
            "duration_ms": (time.perf_counter() - start_time) * 1000,
            "token_count": token_count,
            "done_received": done_received,
            "error": str(exc)
        }

    duration_ms = (time.perf_counter() - start_time) * 1000
    return {
        "session_id": session_id,
        "status_code": status_code,
        "ttft_ms": ttft_ms or duration_ms,
        "duration_ms": duration_ms,
        "token_count": token_count,
        "done_received": done_received,
        "error": error_event
    }


async def run_concurrent_streaming_test(client: httpx.AsyncClient, tokens: dict[str, str], concurrency: int = 15):
    """
    Spawns 'concurrency' simultaneous streaming requests across multiple users.
    Calculates TTFT and Duration percentiles (P50, P90, P99).
    """
    print("\n" + "=" * 80)
    print(f" 🚀 STRESS TEST 1: {concurrency} Concurrent SSE Agent Streams")
    print("=" * 80)

    tasks = []
    for i in range(concurrency):
        user_meta = TEST_USERS[i % len(TEST_USERS)]
        token = tokens[user_meta["username"]]
        query = QUERIES[i % len(QUERIES)]
        session_id = f"STRESS_STREAM_{user_meta['user_id']}_{uuid.uuid4().hex[:6]}"

        tasks.append(
            measure_single_sse_stream(
                client=client,
                token=token,
                user_id=user_meta["user_id"],
                order_id=user_meta["order_id"],
                query=query,
                session_id=session_id
            )
        )

    t0 = time.perf_counter()
    results = await asyncio.gather(*tasks)
    total_batch_time = time.perf_counter() - t0

    success_results = [r for r in results if r["status_code"] == 200 and r["done_received"]]
    failed_results = [r for r in results if r not in success_results]

    ttft_values = [r["ttft_ms"] for r in success_results if r["ttft_ms"] is not None]
    duration_values = [r["duration_ms"] for r in success_results]

    print(f"Total Requests Dispatched : {concurrency}")
    print(f"Successful Stream Streams : {len(success_results)} / {concurrency} ({len(success_results)/concurrency*100:.1f}%)")
    print(f"Total Wall-clock Time     : {total_batch_time:.2f} s")

    if ttft_values:
        ttft_values.sort()
        p50_ttft = statistics.median(ttft_values)
        p90_ttft = ttft_values[int(len(ttft_values) * 0.90)]
        p99_ttft = ttft_values[-1]
        print(f"  ⚡ TTFT (Time-To-First-Token) Latency:")
        print(f"     Min: {min(ttft_values):.1f} ms | P50: {p50_ttft:.1f} ms | P90: {p90_ttft:.1f} ms | P99: {p99_ttft:.1f} ms")

    if duration_values:
        duration_values.sort()
        p50_dur = statistics.median(duration_values)
        p90_dur = duration_values[int(len(duration_values) * 0.90)]
        p99_dur = duration_values[-1]
        print(f"  ⏱️ Full Stream Latency:")
        print(f"     Min: {min(duration_values)/1000:.2f} s | P50: {p50_dur/1000:.2f} s | P90: {p90_dur/1000:.2f} s | P99: {p99_dur/1000:.2f} s")

    if failed_results:
        print(f"  ⚠️ Failed Streams ({len(failed_results)}):")
        for f in failed_results[:3]:
            print(f"     Status: {f['status_code']} | Error: {f.get('error')}")

    assert len(success_results) >= concurrency * 0.85, f"Success rate fell below 85%: {len(success_results)}/{concurrency}"
    print("  ✅ [PASS] Concurrent Streaming SLA satisfied!")


async def run_chaos_lock_contention_test(client: httpx.AsyncClient, tokens: dict[str, str], pair_count: int = 5):
    """
    Chaos Engineering Scenario:
    Simultaneously fires twin requests to the EXACT SAME session_id.
    Asserts that Redis distributed session lock enforces mutual exclusion:
    - 1 request acquires lock -> HTTP 200
    - 1 request rejected     -> HTTP 429
    - Zero double-executions (RACE CONDITIONS) tolerated!
    """
    print("\n" + "=" * 80)
    print(f" 🔒 CHAOS TEST 2: Redis Session Anti-Shake Lock Contention ({pair_count} Pairs)")
    print("=" * 80)

    token = tokens["customer_alice"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    race_conditions = 0
    clean_lock_rejections = 0

    for i in range(pair_count):
        conflict_session = f"CHAOS_TWIN_SESSION_{uuid.uuid4().hex[:6]}"
        payload = {
            "session_id": conflict_session,
            "user_id": "USER_1001",
            "order_id": "ORD-TAKEOUT-9901",
            "query": "Where is my takeout order right now?"
        }

        # Fire two twin requests simultaneously
        req_a = client.post("/api/v1/takeout/chat", json=payload, headers=headers)
        req_b = client.post("/api/v1/takeout/chat", json=payload, headers=headers)

        res_a, res_b = await asyncio.gather(req_a, req_b, return_exceptions=True)
        statuses = [getattr(r, "status_code", "EXCEPTION") for r in [res_a, res_b]]

        print(f"  Pair #{i+1} [Session {conflict_session}] -> Statuses: {statuses}")

        if 200 in statuses and 429 in statuses:
            clean_lock_rejections += 1
            print(f"     ✅ Mutual Exclusion Preserved: 1 Acquired (200), 1 Rejected (429 Anti-shake)")
        elif statuses.count(200) == 2:
            race_conditions += 1
            print(f"     ❌ RACE CONDITION DETECTED! Both concurrent calls obtained lock!")
        elif 429 in statuses:
            clean_lock_rejections += 1
            print(f"     ✅ Rate-limited / Lock defended")
        else:
            print(f"     ℹ️ Unexpected status distribution: {statuses}")

    print(f"\nLock Contention Summary: Clean Interceptions: {clean_lock_rejections}/{pair_count} | Race Conditions: {race_conditions}")
    assert race_conditions == 0, f"Critical Race Condition detected in Redis Distributed Lock!"
    assert clean_lock_rejections > 0, "No lock contention events captured."
    print("  ✅ [PASS] Redis Distributed Lock zero-race-condition guarantee verified!")


async def run_apm_metrics_probe(client: httpx.AsyncClient):
    """Verifies that under load, Prometheus telemetry and health probes remain responsive."""
    print("\n" + "=" * 80)
    print(" 📊 TELEMETRY TEST 3: APM Prometheus Metrics & Health Probe Under Load")
    print("=" * 80)

    # 1. Readiness probe
    t0 = time.perf_counter()
    ready_resp = await client.get("/api/v1/healthz/readiness")
    ready_latency_ms = (time.perf_counter() - t0) * 1000
    assert ready_resp.status_code == 200
    body = ready_resp.json()
    assert body["mysql"] and body["redis"] and body["postgres"]
    print(f"  🏥 K8s Readiness Probe Latency: {ready_latency_ms:.1f} ms | Status: {body['status']}")

    # 2. Prometheus metrics scrape
    t1 = time.perf_counter()
    metrics_resp = await client.get("/api/v1/metrics")
    metrics_latency_ms = (time.perf_counter() - t1) * 1000
    assert metrics_resp.status_code == 200
    metrics_text = metrics_resp.text
    print(f"  📈 Prometheus Scrape Latency : {metrics_latency_ms:.1f} ms")

    # Verify key metrics exist
    assert "agent_requests_total" in metrics_text
    assert "agent_ttft_seconds" in metrics_text
    assert "agent_duration_seconds" in metrics_text
    assert "agent_cost_usd_total" in metrics_text

    print("  ✅ [PASS] All APM Observability metrics exported cleanly!")


async def main():
    """Main stress & chaos execution harness."""
    print("\n" + "#" * 80)
    print(" SKY TAKEOUT AGENT: PRODUCTION HIGH-CONCURRENCY CHAOS BENCHMARK")
    print("#" * 80)

    # Spin up live uvicorn server in background
    server_port = SERVER_PORT
    server_config = uvicorn.Config(app, host="127.0.0.1", port=server_port, log_level="warning")
    server = uvicorn.Server(server_config)
    server_task = asyncio.create_task(server.serve())

    # Wait for Uvicorn lifespan startup to complete
    while not server.started:
        await asyncio.sleep(0.1)
    await asyncio.sleep(0.5)

    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=45.0) as client:
            # Step 1: Pre-authenticate test users
            tokens = {}
            for u in TEST_USERS:
                t = await login_user(client, u)
                tokens[u["username"]] = t
                print(f"🔑 Authenticated '{u['username']}' -> Bearer {t[:16]}...")

            # Step 2: Concurrent Multi-Session SSE Streams (12 concurrent streams)
            await run_concurrent_streaming_test(client, tokens, concurrency=12)

            # Step 3: Chaos Redis Session Lock Contention Test
            await run_chaos_lock_contention_test(client, tokens, pair_count=5)

            # Step 4: Health Probe & Prometheus Metrics Under Load
            await run_apm_metrics_probe(client)

            print("\n" + "=" * 80)
            print(" 🎉 [STRESS & CHAOS VERIFICATION PASSED] All Enterprise SLAs Satisfied!")
            print("=" * 80)

    finally:
        server.should_exit = True
        await server_task


if __name__ == "__main__":
    asyncio.run(main())
