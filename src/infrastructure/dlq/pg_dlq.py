"""PostgreSQL-backed Dead Letter Queue."""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import DLQMessageModel
from src.infrastructure.dlq import DeadLetterQueue

logger = logging.getLogger(__name__)


class PgDLQ(DeadLetterQueue):
    """PostgreSQL implementation of DeadLetterQueue."""

    def __init__(self, session: AsyncSession):
        super().__init__()
        self._session = session

    async def enqueue(
        self,
        event_type: str,
        payload: dict[str, Any],
        error: str,
        retry_count: int = 0,
    ) -> None:
        """Enqueue a failed event to the DLQ in Postgres."""
        dlq_message = DLQMessageModel(
            event_type=event_type,
            payload=json.dumps(payload),
            error=error,
            retry_count=retry_count,
        )
        self._session.add(dlq_message)
        # Flush to ensure it's written in the current transaction
        await self._session.flush()
        logger.error(f"PgDLQ: Enqueued {event_type} — {error}")

    @property
    def size(self) -> int:
        """Returns the local queue size, unsupported for PG.
        Raises NotImplementedError because counting DB rows synchronously inside
        a property is not feasible. Use `get_all` instead.
        """
        raise NotImplementedError("Size property not supported for PgDLQ")

    async def get_all(self) -> list[dict[str, Any]]:
        """Retrieve all messages from the DLQ table."""
        stmt = select(DLQMessageModel).order_by(DLQMessageModel.created_at.asc())
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        
        return [
            {
                "id": model.id,
                "event_type": model.event_type,
                "payload": json.loads(model.payload),
                "error": model.error,
                "retry_count": model.retry_count,
                "created_at": model.created_at,
            }
            for model in models
        ]
