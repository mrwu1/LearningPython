import json
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field


class SSEEventType(str, Enum):
    TOKEN = "token"                   # Live LLM token delta
    THOUGHT = "thought"               # Reasoning / thinking delta
    PROGRESS = "progress"             # Specialist internal stage progress
    CARD = "card"                     # Interactive UI card (e.g. dish recommendations)
    NODE_UPDATE = "node_update"       # LangGraph superstep node transition
    INTERRUPT = "interrupt"           # Dynamic human-in-the-loop breakpoint
    DONE = "done"                     # Final completion signal with usage metrics
    ERROR = "error"                   # Sanitized error event
    PING = "ping"                     # Keep-alive heartbeat packet


class SSEEvent(BaseModel):
    """Universal SSE Protocol Model conforming to W3C EventSource standards."""
    event: SSEEventType
    data: dict[str, Any] = Field(default_factory=dict)
    event_id: Optional[str] = None
    retry_ms: Optional[int] = None

    def to_sse_dict(self) -> dict[str, str]:
        """Formats into starlette EventSourceResponse dict structure."""
        out = {
            "event": self.event.value,
            "data": json.dumps(self.data, ensure_ascii=False)
        }
        if self.event_id:
            out["id"] = self.event_id
        if self.retry_ms:
            out["retry"] = str(self.retry_ms)
        return out
