import json
import random
import time
import uuid
from locust import HttpUser, task, between, events
from locust.exception import StopUser


# Sample pool of registered test users in MySQL
TEST_USERS = [
    {"username": "customer_alice", "password": "123456", "user_id": "USER_1001", "order_id": "ORD-TAKEOUT-9901"},
    {"username": "customer_bob", "password": "123456", "user_id": "USER_1002", "order_id": "ORD-TAKEOUT-9902"},
    {"username": "customer_charlie", "password": "123456", "user_id": "USER_1003", "order_id": "ORD-TAKEOUT-9903"},
]

DISH_QUERIES = [
    "Could you recommend a low-calorie lunch bento under 500 kcal?",
    "Recommend a healthy dinner with salmon or chicken breast.",
    "What delicious high-protein meals do you have today?",
    "I want something light and nutritious with avocados.",
]


class SkyTakeoutAgentUser(HttpUser):
    """
    Locust load testing client for Sky Takeout Multi-Agent Gateway.
    Simulates real-world customer behaviors:
    1. Authenticates via JWT.
    2. Streams multi-channel agent tokens over SSE with TTFT tracking.
    3. Triggers rapid concurrent session bursts to verify Redis lock anti-shake.
    4. Continuously checks K8s readiness probes and Prometheus metrics.
    """
    wait_time = between(1.0, 3.0)

    def on_start(self):
        """Authenticates user and obtains JWT Bearer token upon worker startup."""
        self.user_info = random.choice(TEST_USERS)
        self.user_id = self.user_info["user_id"]
        self.order_id = self.user_info["order_id"]
        self.headers = {"Content-Type": "application/json"}

        # Perform login
        login_payload = {
            "username": self.user_info["username"],
            "password": self.user_info["password"]
        }
        with self.client.post("/api/v1/auth/login", json=login_payload, catch_response=True) as resp:
            if resp.status_code == 200:
                token_data = resp.json()
                self.token = token_data.get("access_token")
                self.headers["Authorization"] = f"Bearer {self.token}"
            else:
                resp.failure(f"Failed to authenticate user {self.user_info['username']}: {resp.status_code}")
                raise StopUser()

    @task(5)
    def stream_dish_recommendation(self):
        """
        Scenario 1: SSE Streaming Food Recommendation.
        Measures Time-To-First-Token (TTFT) and full token stream completion duration.
        """
        session_id = f"SESSION_LOCUST_DISH_{self.user_id}_{uuid.uuid4().hex[:8]}"
        query = random.choice(DISH_QUERIES)

        payload = {
            "session_id": session_id,
            "user_id": self.user_id,
            "order_id": self.order_id,
            "query": query
        }

        start_time = time.time()
        ttft = None
        token_count = 0
        done_received = False
        error_msg = None

        try:
            with self.client.post(
                "/api/v1/takeout/chat",
                json=payload,
                headers=self.headers,
                stream=True,
                catch_response=True,
                name="[SSE] Stream Dish Recommendation"
            ) as resp:
                if resp.status_code != 200:
                    resp.failure(f"Unexpected status code: {resp.status_code}")
                    return

                current_event = None
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line_str = line.decode("utf-8") if isinstance(line, bytes) else line

                    if line_str.startswith("event: "):
                        current_event = line_str.replace("event: ", "").strip()
                    elif line_str.startswith("data: "):
                        raw_data = line_str.replace("data: ", "").strip()

                        # First token or content received -> record TTFT
                        if current_event == "token" and ttft is None:
                            ttft = (time.time() - start_time) * 1000
                            events.request.fire(
                                request_type="SSE_TTFT",
                                name="[Metric] Time To First Token (TTFT)",
                                response_time=ttft,
                                response_length=0,
                                exception=None
                            )

                        if current_event == "token":
                            token_count += 1
                        elif current_event == "done":
                            done_received = True
                        elif current_event == "error":
                            error_msg = raw_data

                duration_ms = (time.time() - start_time) * 1000
                if done_received:
                    resp.success()
                elif error_msg:
                    resp.failure(f"Stream returned error: {error_msg}")
                else:
                    resp.failure("Stream ended prematurely without 'done' event.")

        except Exception as exc:
            events.request.fire(
                request_type="SSE_STREAM",
                name="[SSE] Stream Dish Recommendation",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=exc
            )

    @task(3)
    def stream_order_courier_tracking(self):
        """
        Scenario 2: Real-time Order & Courier GPS Tracking.
        Queries live delivery status and measures gateway latency.
        """
        session_id = f"SESSION_LOCUST_ORDER_{self.user_id}_{uuid.uuid4().hex[:8]}"
        payload = {
            "session_id": session_id,
            "user_id": self.user_id,
            "order_id": self.order_id,
            "query": f"Where is my courier for order {self.order_id} right now?"
        }

        start_time = time.time()
        ttft = None
        done_received = False

        try:
            with self.client.post(
                "/api/v1/takeout/chat",
                json=payload,
                headers=self.headers,
                stream=True,
                catch_response=True,
                name="[SSE] Stream Order Tracking"
            ) as resp:
                if resp.status_code != 200:
                    resp.failure(f"HTTP {resp.status_code}")
                    return

                current_event = None
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                    if line_str.startswith("event: "):
                        current_event = line_str.replace("event: ", "").strip()
                    elif line_str.startswith("data: "):
                        if current_event == "token" and ttft is None:
                            ttft = (time.time() - start_time) * 1000
                            events.request.fire(
                                request_type="SSE_TTFT",
                                name="[Metric] Time To First Token (TTFT)",
                                response_time=ttft,
                                response_length=0,
                                exception=None
                            )
                        if current_event == "done":
                            done_received = True

                if done_received:
                    resp.success()
                else:
                    resp.failure("Missing 'done' event in order tracking stream.")

        except Exception as exc:
            events.request.fire(
                request_type="SSE_STREAM",
                name="[SSE] Stream Order Tracking",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=exc
            )

    @task(2)
    def test_rapid_session_lock_contention(self):
        """
        Scenario 3: Chaos Burst - Redis Distributed Lock Anti-Shake Verification.
        Simulates aggressive double-clicking on the same thread_id:
        Sends 2 rapid requests sequentially/nearly simultaneously.
        Asserts that Redis distributed lock rejects the concurrent duplicate with HTTP 429!
        """
        conflict_session_id = f"CHAOS_LOCK_BURST_{self.user_id}_{uuid.uuid4().hex[:6]}"
        payload = {
            "session_id": conflict_session_id,
            "user_id": self.user_id,
            "order_id": self.order_id,
            "query": "Checking lock concurrency protection."
        }

        # Request 1 initiates stream
        resp1 = self.client.post(
            "/api/v1/takeout/chat",
            json=payload,
            headers=self.headers,
            stream=True,
            name="[Lock Chaos] Request 1 (Acquires Lock)"
        )

        # Request 2 fired immediately on SAME session_id
        resp2 = self.client.post(
            "/api/v1/takeout/chat",
            json=payload,
            headers=self.headers,
            name="[Lock Chaos] Request 2 (Expect 429 Conflict)"
        )

        # Drain resp1 to release lock cleanly
        try:
            for _ in resp1.iter_lines():
                pass
        except Exception:
            pass

        # Validation: resp2 MUST be 429 (or 409) due to lock contention
        if resp2.status_code == 429:
            events.request.fire(
                request_type="CHAOS_LOCK",
                name="[Chaos] Redis Session Anti-Shake Lock 429",
                response_time=resp2.elapsed.total_seconds() * 1000,
                response_length=len(resp2.content),
                exception=None
            )
        elif resp2.status_code == 200:
            events.request.fire(
                request_type="CHAOS_LOCK",
                name="[Chaos] Redis Session Anti-Shake Lock 429",
                response_time=resp2.elapsed.total_seconds() * 1000,
                response_length=len(resp2.content),
                exception=Exception(
                    f"RACE CONDITION DETECTED! Both concurrent requests on session '{conflict_session_id}' got 200 OK!"
                )
            )

    @task(2)
    def check_health_readiness(self):
        """Scenario 4: Probes K8s Readiness (MySQL, Redis, PostgreSQL)."""
        with self.client.get("/api/v1/healthz/readiness", catch_response=True, name="[Probe] Readiness Check") as resp:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("mysql") and data.get("redis") and data.get("postgres"):
                    resp.success()
                else:
                    resp.failure(f"Unhealthy dependency detected: {data}")
            else:
                resp.failure(f"Readiness check failed with status {resp.status_code}")

    @task(1)
    def scrape_prometheus_metrics(self):
        """Scenario 5: Prometheus telemetry scrape endpoint check."""
        with self.client.get("/api/v1/metrics", catch_response=True, name="[APM] Prometheus Scrape") as resp:
            if resp.status_code == 200 and "agent_requests_total" in resp.text:
                resp.success()
            else:
                resp.failure(f"Prometheus scrape failed or missing agent metrics (Status: {resp.status_code})")
