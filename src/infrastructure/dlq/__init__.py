"""Dead Letter Queue — Captures failed events for inspection and retry."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class DeadLetterQueue:
    """In-memory DLQ for failed event processing.

    In production, this would be backed by a persistent store
    (e.g., Redis list, PostgreSQL table, or a dedicated queue).
    """

    def __init__(self):
        self._messages: list[dict[str, Any]] = []

    async def enqueue(
        self,
        event_type: str,
        payload: dict[str, Any],
        error: str,
        retry_count: int = 0,
    ) -> None:
        self._messages.append(
            {
                "id": uuid4(),
                "event_type": event_type,
                "payload": payload,
                "error": error,
                "retry_count": retry_count,
                "created_at": datetime.now(timezone.utc),
            }
        )
        logger.error(f"DLQ: {event_type} failed — {error}")

    @property
    def size(self) -> int:
        return len(self._messages)

    async def get_all(self) -> list[dict[str, Any]]:
        return list(self._messages)
