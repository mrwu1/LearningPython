from typing import AsyncIterator, Any
from langchain_core.messages import AIMessageChunk
from app.core.streaming.protocol import SSEEvent, SSEEventType


class LangGraphStreamAdapter:
    """Transforms raw LangGraph astream multi-mode events into standardized SSEEvents."""

    def __init__(self, trace_id: str, masked_nodes: set[str] | None = None):
        self.trace_id = trace_id
        # Nodes whose raw tokens should not be streamed to user (e.g., router/evaluator)
        self.masked_nodes = masked_nodes or {"supervisor"}

    async def transform(self, raw_stream: AsyncIterator[tuple[str, Any]]) -> AsyncIterator[SSEEvent]:
        async for mode, payload in raw_stream:
            # 1. Message Stream: Token-level deltas
            if mode == "messages":
                msg, metadata = payload
                node_name = metadata.get("langgraph_node", "")
                if node_name in self.masked_nodes:
                    continue

                if isinstance(msg, AIMessageChunk):
                    # Thought/Reasoning stream (e.g. DeepSeek-R1)
                    thought_delta = msg.additional_kwargs.get("reasoning_content")
                    if thought_delta:
                        yield SSEEvent(
                            event=SSEEventType.THOUGHT,
                            data={"node": node_name, "delta": thought_delta, "trace_id": self.trace_id}
                        )

                    # Text token delta
                    if msg.content and isinstance(msg.content, str):
                        yield SSEEvent(
                            event=SSEEventType.TOKEN,
                            data={"node": node_name, "delta": msg.content, "trace_id": self.trace_id}
                        )

            # 2. Custom Stream: Emitted by specialists via StreamWriter
            elif mode == "custom":
                if isinstance(payload, dict) and payload.get("type") == "card":
                    yield SSEEvent(
                        event=SSEEventType.CARD,
                        data={"card": payload, "trace_id": self.trace_id}
                    )
                else:
                    yield SSEEvent(
                        event=SSEEventType.PROGRESS,
                        data={"progress": payload, "trace_id": self.trace_id}
                    )

            # 3. Superstep Node Transitions
            elif mode == "updates":
                nodes = list(payload.keys())
                yield SSEEvent(
                    event=SSEEventType.NODE_UPDATE,
                    data={"nodes": nodes, "trace_id": self.trace_id}
                )
