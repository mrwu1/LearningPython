# Sky Takeout Enterprise Multi-Agent System (苍穹外卖智能体微服务)

Production-grade, enterprise-ready multi-agent system powered by **LangGraph**, **FastAPI**, **SQLAlchemy 2.0 (Async)**, **Alembic**, **Redis**, and **PostgreSQL (Checkpointer)**.

---

## 🌟 Key Architectural Highlights

1. **Zero In-Memory Fakes**:
   - **MySQL 8.0**: Persistent domain data (dishes inventory with row locks, live orders, refund ledgers).
   - **PostgreSQL 16**: LangGraph checkpoint snapshots managed via `AsyncPostgresSaver` and `AsyncConnectionPool`.
   - **Redis**: Distributed concurrency lock with Lua safe-release script, preventing race conditions and duplicate clicks.

2. **Clean Architecture / DDD**:
   - `core/`: Config settings (`pydantic-settings`), Async DB Engine, Redis mutex lock, LLM client.
   - `models/`: SQLAlchemy 2.0 declarative ORM entities with Alembic version-controlled DDL migrations.
   - `repositories/`: Transaction-safe data access layer with pessimistic locking (`with_for_update()`) and idempotency guarantees.
   - `schemas/`: Pydantic V2 state models and request/response DTOs.
   - `services/agent/`: Modular multi-agent engine:
     - `supervisor.py`: Dual-guard orchestration (deterministic 0ms/0-token exit + dynamic LLM routing).
     - `specialists/`: `dish_advisor`, `order_manager`, `refund_officer` with dynamic `interrupt()`.
     - `tools/`: Async tools bound to live DB sessions with graceful failure handling.
     - `graph_factory.py`: Compiled production graph factory with PostgreSQL pooling.
   - `api/`: REST & SSE endpoints, TraceID middleware (`X-Request-ID`), K8s liveness & readiness health probes.

3. **Enterprise Resilience & Observability**:
   - Full Trace ID propagation (`contextvars`) across FastAPI, Loguru, and LangGraph state.
   - Dynamic human-in-the-loop review via `interrupt()` and resumption via `Command(resume=...)`.

---

## 🏗️ Directory Layout

```text
sky_takeout_system/
├── alembic/                    # Database versioned migrations
│   ├── env.py
│   └── versions/               # DDL revision files
├── alembic.ini
├── docs/
│   └── experts_workflow_breakdown.md # 架构拆分与三大专家（点餐、派送、退款）流程图解
├── Dockerfile                  # Multi-stage production container build
├── docker-compose.yml          # Full-stack orchestrator (App + MySQL + Redis + Postgres)
├── pyproject.toml              # Dependencies & project metadata (managed by uv)
├── scripts/
│   └── seed_data.sql           # Clean SQL seed script for Dishes & Orders
├── src/
│   └── app/
│       ├── api/                # API Gateways, SSE streaming & HITL approval
│       ├── core/               # Config, Database, Redis, LLM, Logging
│       ├── models/             # SQLAlchemy ORM models
│       ├── repositories/       # Async Repositories (ACID & Idempotency)
│       ├── schemas/            # Pydantic state & DTO models
│       ├── services/agent/     # LangGraph Multi-Agent Engine
│       └── main.py             # FastAPI App & Lifespan management
└── tests/
    └── test_live_gateway.py    # E2E live integration & scenario test suite
```

---

## 🚀 Quickstart & Local Development

### 1. Requirements
- Python 3.12+
- `uv` package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

### 2. Environment Configuration
Create a `.env` file in the root directory:
```ini
APP_NAME=SkyTakeoutSystem
APP_PORT=8000
ENV_MODE=dev
LOG_LEVEL=INFO

# MySQL 8.0
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DB=sky_takeout_agent

# Redis
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password
REDIS_DB=0

# PostgreSQL (LangGraph State Checkpointer)
PG_HOST=127.0.0.1
PG_PORT=5432
PG_USER=postgres
PG_PASSWORD=your_pg_password
PG_DB=agent_prod

# LLM Gateway
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

### 3. Database Migrations & Seeding
```bash
# Run Alembic migrations
uv run alembic upgrade head

# Seed initial dishes & orders
mysql -h 127.0.0.1 -u root -p sky_takeout_agent < scripts/seed_data.sql
```

### 4. Running the Microservice
```bash
# Direct run
uv run python main.py

# Or via uvicorn CLI
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 5. Running the End-to-End Live Test
```bash
uv run python tests/test_live_gateway.py
```

---

## 🐳 Docker Container Deployment

To launch the entire stack (Gateway + MySQL + Redis + PostgreSQL) in isolated containers:

```bash
docker compose up -d --build
```
Check service health:
```bash
curl http://127.0.0.1:8000/api/v1/healthz/readiness
```
