from langgraph.graph import StateGraph
from langgraph.types import RetryPolicy, TimeoutPolicy
from opentelemetry.sdk import error_handler


def node_a():
    pass

builder = StateGraph()

builder.add_node(
    "node_a",
    node_a,
    retry_policy=RetryPolicy(
        max_attempts=3,
        jitter=False # concurrency - 打散 - True default
    ),
    timeout=TimeoutPolicy(),
    # error_handler=error_handler(
    #
    # )
)

try:
    # graph.invoke({})
    pass
except Exception as e:
    print(e)