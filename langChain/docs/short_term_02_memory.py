from langchain.agents import create_agent
from langgraph.checkpoint.postgres import PostgresSaver


def get_user_info() -> str:
    """Look up information about the current user."""
    return "No user profile on file."

DB_URI = "postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable"
with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup() # auto create tables in PostgreSQL
    agent = create_agent(
        "gpt-5.5",
        tools=[get_user_info],
        checkpointer=checkpointer,
    )