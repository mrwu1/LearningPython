from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from langgraph.store.base import BaseStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from loguru import logger
from app.core.config import settings
from app.schemas.agent_state import SkyTakeoutState
from app.services.agent.supervisor import supervisor_node, route_from_supervisor
from app.services.agent.specialists.dish_advisor import dish_advisor_worker
from app.services.agent.specialists.order_manager import order_manager_worker
from app.services.agent.specialists.refund_officer import refund_officer_worker


def get_pg_connection_string() -> str:
    """Builds standard libpq connection URI for PostgreSQL checkpointer."""
    return (
        f"postgresql://{settings.PG_USER}:{settings.PG_PASSWORD}"
        f"@{settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_DB}"
    )


def create_sky_takeout_graph(
        checkpointer: BaseCheckpointSaver,
        store:Optional[BaseStore] = None,# 👈 增加可选的全局 Store 参数
):
    """
    Assembles and compiles the Sky Takeout Multi-Agent StateGraph.
    Decoupled from checkpointer implementation for easy testing and multi-environment deployment.
    """
    builder = StateGraph(SkyTakeoutState)

    # 1. Register core nodes
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("dish_advisor", dish_advisor_worker)
    builder.add_node("order_manager", order_manager_worker)
    builder.add_node("refund_officer", refund_officer_worker)

    # 2. Wire topological edges
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges("supervisor", route_from_supervisor)

    # Return to supervisor for closed-loop triage
    builder.add_edge("dish_advisor", "supervisor")
    builder.add_edge("order_manager", "supervisor")
    builder.add_edge("refund_officer", "supervisor")

    # 3. Bind persistent checkpointer and compile
    return builder.compile(checkpointer=checkpointer,store=store)


@asynccontextmanager
async def init_production_graph() -> AsyncGenerator:
    """
    Production Engine Lifespan Factory:
    Initializes PostgreSQL connection pool, ensures checkpointer schema tables exist (ONCE on boot),
    and yields the compiled production graph ready for concurrent traffic.
    """
    conn_string = get_pg_connection_string()
    logger.info(f"🐘 [PostgresSaver] Initializing checkpointer pool on {settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_DB}...")

    async with AsyncConnectionPool(
        conninfo=conn_string,
        max_size=20,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    ) as pool:
        checkpointer = AsyncPostgresSaver(conn=pool)
        # Production standard: execute setup() once on startup to guarantee tables exist
        await checkpointer.setup()
        logger.info("✅ [PostgresSaver] Checkpointer schema verified and tables ready.")
        
        compiled_graph = create_sky_takeout_graph(checkpointer=checkpointer)
        yield compiled_graph
