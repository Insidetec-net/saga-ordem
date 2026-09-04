"""Saga Log — Audit trail for saga step execution."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from src.domain import SagaState


class SagaLogRepository(ABC):
    """Abstract saga log for auditing and debugging."""

    @abstractmethod
    async def log_step(
        self,
        order_id: UUID,
        saga_id: UUID,
        step_name: str,
        state: SagaState,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None: ...

    @abstractmethod
    async def get_saga_history(
        self, saga_id: UUID
    ) -> list[dict[str, Any]]: ...


class InMemorySagaLog(SagaLogRepository):
    """In-memory saga log for tests."""

    def __init__(self):
        self._logs: list[dict[str, Any]] = []

    async def log_step(
        self,
        order_id: UUID,
        saga_id: UUID,
        step_name: str,
        state: SagaState,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self._logs.append(
            {
                "id": uuid4(),
                "order_id": order_id,
                "saga_id": saga_id,
                "step_name": step_name,
                "state": state.name,
                "payload": payload,
                "error": error,
                "created_at": datetime.now(timezone.utc),
            }
        )

    async def get_saga_history(
        self, saga_id: UUID
    ) -> list[dict[str, Any]]:
        return [entry for entry in self._logs if entry["saga_id"] == saga_id]
