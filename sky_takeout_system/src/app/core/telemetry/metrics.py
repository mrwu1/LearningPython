from prometheus_client import Counter, Histogram, Gauge

# 1. Request throughput & status counter
AGENT_REQUESTS_TOTAL = Counter(
    "agent_requests_total",
    "Total incoming agent requests processed",
    ["status"]  # 'success', 'error', 'interrupt'
)

# 2. Time-To-First-Token (TTFT) latency distribution
AGENT_TTFT_SECONDS = Histogram(
    "agent_ttft_seconds",
    "Time elapsed before emitting the very first token to client",
    buckets=[0.1, 0.2, 0.5, 0.8, 1.2, 2.0, 5.0, 10.0]
)

# 3. Total stream duration latency distribution
AGENT_DURATION_SECONDS = Histogram(
    "agent_duration_seconds",
    "Total end-to-end stream duration in seconds",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
)

# 4. Token consumption counter by model and type
AGENT_TOKENS_TOTAL = Counter(
    "agent_tokens_total",
    "Total tokens consumed across all agent LLM invocations",
    ["model", "type"]  # type: 'prompt', 'completion'
)

# 5. Financial cost counter accumulated in USD
AGENT_COST_USD_TOTAL = Counter(
    "agent_cost_usd_total",
    "Total estimated financial cost accumulated in USD"
)

# 6. Current active streaming sessions (concurrent connection gauge)
AGENT_ACTIVE_SESSIONS = Gauge(
    "agent_active_sessions",
    "Current active SSE streaming sessions connected"
)
