import uuid
from enum import Enum
from typing import Any, Callable, Coroutine, Optional


class SagaStatus(str, Enum):
    """Lifecycle status states for distributed Saga transactions."""
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"


class SagaContext:
    """
    Saga Context Blackboard:
    Thread-safe, state-passing container across forward steps and reverse compensation handlers.
    """

    def __init__(self, initial_data: Optional[dict[str, Any]] = None, tx_id: Optional[str] = None):
        self.tx_id: str = tx_id or f"TX_SAGA_{uuid.uuid4().hex[:12].upper()}"
        self.status: SagaStatus = SagaStatus.PENDING
        self.data: dict[str, Any] = initial_data.copy() if initial_data else {}
        self.execution_history: list[str] = []
        self.error: Optional[str] = None

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    def record_step(self, step_name: str) -> None:
        self.execution_history.append(step_name)


# Type aliases for async step callbacks
AsyncStepAction = Callable[[SagaContext], Coroutine[Any, Any, Any]]
AsyncReconcileAction = Callable[[SagaContext], Coroutine[Any, Any, dict[str, Any]]]


class SagaStep:
    """
    Atomic Saga Transaction Step:
    Encapsulates forward action, reverse compensation callback, and optional reconciliation check.
    """

    def __init__(
        self,
        name: str,
        forward: AsyncStepAction,
        compensate: Optional[AsyncStepAction] = None,
        reconcile: Optional[AsyncReconcileAction] = None,
    ):
        self.name: str = name
        self.forward: AsyncStepAction = forward
        self.compensate: Optional[AsyncStepAction] = compensate
        self.reconcile: Optional[AsyncReconcileAction] = reconcile
