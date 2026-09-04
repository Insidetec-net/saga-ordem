"""Outbox Repository — Transactional outbox for reliable event delivery."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from src.domain import DomainEvent
from src.infrastructure.serialization import DomainEncoder


class OutboxRepository(ABC):
    """Abstract outbox for reliable event publishing (Outbox Pattern)."""

    @abstractmethod
    async def append(self, event: DomainEvent, aggregate_id: UUID) -> None: ...

    @abstractmethod
    async def get_pending(
        self, batch_size: int = 100
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def mark_sent(self, outbox_id: UUID) -> None: ...

    @abstractmethod
    async def mark_failed(self, outbox_id: UUID, error: str) -> None: ...


class InMemoryOutbox(OutboxRepository):
    """In-memory outbox implementation for tests."""

    def __init__(self):
        self._messages: list[dict[str, Any]] = []

    async def append(self, event: DomainEvent, aggregate_id: UUID) -> None:
        self._messages.append(
            {
                "id": uuid4(),
                "aggregate_id": aggregate_id,
                "event_type": event.event_type,
                "payload": json.dumps(event.__dict__, cls=DomainEncoder),
                "created_at": datetime.now(timezone.utc),
                "sent": False,
                "failed": False,
            }
        )

    async def get_pending(
        self, batch_size: int = 100
    ) -> list[dict[str, Any]]:
        return [
            m
            for m in self._messages
            if not m["sent"] and not m["failed"]
        ][:batch_size]

    async def mark_sent(self, outbox_id: UUID) -> None:
        for m in self._messages:
            if m["id"] == outbox_id:
                m["sent"] = True

    async def mark_failed(self, outbox_id: UUID, error: str) -> None:
        for m in self._messages:
            if m["id"] == outbox_id:
                m["failed"] = True
                m["error"] = error
