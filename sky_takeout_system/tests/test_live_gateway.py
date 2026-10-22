import asyncio
import json
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import httpx
import uvicorn
from loguru import logger
from app.core.config import settings
from app.main import app


async def run_full_enterprise_gateway_test():
    """
    Spins up live uvicorn server in background on port 8000,
    and runs comprehensive E2E tests against live MySQL, Redis, and PostgreSQL!
    """
    server_port = 8000
    server_config = uvicorn.Config(app, host="127.0.0.1", port=server_port, log_level="warning")
    server = uvicorn.Server(server_config)
    server_task = asyncio.create_task(server.serve())
    # 等待 Uvicorn Lifespan 完全就绪 (server.started 为 True 代表 Lifespan Startup 顺利完成)
    while not server.started:
        await asyncio.sleep(0.2)
    await asyncio.sleep(0.5)

    base_url = f"http://127.0.0.1:{server_port}"
    logger.info(f"🌐 [E2E Live Test] Server running at {base_url}")

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=35.0) as client:
            # -----------------------------------------------------------------
            # 1. 探针测试: K8s 存活探针与三库就绪探针 (MySQL + Redis + PostgreSQL)
            # -----------------------------------------------------------------
            print("\n" + "=" * 70)
            print(" 🏥 PROBE TEST: K8s Liveness & Readiness Probes")
            print("=" * 70)
            live_resp = await client.get("/api/v1/healthz/liveness")
            print(f"Liveness Status: {live_resp.status_code} | Body: {live_resp.json()}")
            assert live_resp.status_code == 200

            ready_resp = await client.get("/api/v1/healthz/readiness")
            print(f"Readiness Status: {ready_resp.status_code} | Body: {ready_resp.json()}")
            assert ready_resp.status_code == 200
            assert ready_resp.json()["mysql"] is True
            assert ready_resp.json()["redis"] is True
            assert ready_resp.json()["postgres"] is True
            print("  ✅ [ALL 3 CLOUD DATABASES HEALTHY] MySQL, Redis, and PostgreSQL passed ping checks!")

            # -----------------------------------------------------------------
            # 2. 售前咨询测试: SSE 流式长连接 (推荐三文鱼轻食)
            # -----------------------------------------------------------------
            print("\n" + "=" * 70)
            print(" 🥗 SCENARIO 1: SSE Streaming Food Recommendation")
            print("=" * 70)
            chat_payload = {
                "session_id": "SESSION_PROD_ADVICE_01",
                "order_id": "ORD-TAKEOUT-9901",
                "query": "I want a healthy low-calorie salmon dinner under 500 kcal."
            }
            async with client.stream("POST", "/api/v1/takeout/chat", json=chat_payload) as resp:
                print(f"HTTP Status: {resp.status_code} | Content-Type: {resp.headers.get('content-type')}")
                current_event = None
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("event: "):
                        current_event = line.replace("event: ", "").strip()
                    elif line.startswith("data: "):
                        raw_data = line.replace("data: ", "").strip()
                        print(f"  [SSE Event: {current_event}] -> {raw_data}")

            # -----------------------------------------------------------------
            # 3. 并发互斥防抖测试: Redis 分布式锁拦截连击 (HTTP 429)
            # -----------------------------------------------------------------
            print("\n" + "=" * 70)
            print(" 🔒 SCENARIO 2: Redis Distributed Session Lock Anti-Shake")
            print("=" * 70)
            busy_payload = {
                "session_id": "RAPID_CONCURRENT_SESSION_02",
                "order_id": "ORD-TAKEOUT-9902",
                "query": "Where is my courier right now?"
            }

            async def send_chat():
                return await client.post("/api/v1/takeout/chat", json=busy_payload)

            req_a, req_b = await asyncio.gather(send_chat(), send_chat(), return_exceptions=True)
            statuses = [getattr(r, "status_code", "ERROR") for r in [req_a, req_b]]
            print(f"Concurrent Status Codes: {statuses}")
            if 429 in statuses:
                print("  ✅ [CLUSTER LOCK SUCCESS] Redis Distributed Lock intercepted race condition with HTTP 429!")

            # -----------------------------------------------------------------
            # 4. 售后大额退款: interrupt() 挂起告警 + 店长后台审批唤醒
            # -----------------------------------------------------------------
            print("\n" + "=" * 70)
            print(" 💰 SCENARIO 3: High-Value Refund ($120) Dynamic Breakpoint & Resume")
            print("=" * 70)
            refund_session = "SESSION_PROD_REFUND_03"
            refund_req = {
                "session_id": refund_session,
                "order_id": "ORD-TAKEOUT-9903",
                "query": "10 steaks arrived freezing cold! I demand a $120 refund immediately!",
                "refund_amount": 120.0,
                "refund_reason": "Icy cold food"
            }

            # 步骤 4.1: 顾客提交退款，SSE 接收挂起告警
            async with client.stream("POST", "/api/v1/takeout/chat", json=refund_req) as resp:
                current_event = None
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("event: "):
                        current_event = line.replace("event: ", "").strip()
                    elif line.startswith("data: "):
                        raw_data = line.replace("data: ", "").strip()
                        if current_event == "human_approval_required":
                            print(f"  🚨 [CRITICAL ALERT RECEIVED OVER SSE]:\n     {raw_data}")

            # 步骤 4.2: 店长在后台审批面板点击“批准退款 $100”
            print("\n  👉 Manager reviews alert and calls /api/v1/takeout/approve to resume graph...")
            approve_req = {
                "session_id": refund_session,
                "decision": "APPROVED",
                "approved_amount": 100.0,
                "notes": "Verified cold steak delivery with courier. Approved $100 settlement."
            }
            approve_resp = await client.post("/api/v1/takeout/approve", json=approve_req)
            print(f"  Approval HTTP Status: {approve_resp.status_code}")
            print(f"  Approval Response Body:\n  {json.dumps(approve_resp.json(), indent=4, ensure_ascii=False)}")

    finally:
        print("\n" + "=" * 70)
        print(" 🏁 E2E TEST COMPLETE - SHUTTING DOWN GATEWAY")
        print("=" * 70)
        server.should_exit = True
        await server_task


if __name__ == "__main__":
    asyncio.run(run_full_enterprise_gateway_test())
