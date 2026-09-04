"""PostgreSQL Outbox Repository — Transactional outbox for reliable events."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain import DomainEvent
from src.infrastructure.database.models import OutboxEventModel
from src.infrastructure.outbox import OutboxRepository
from src.infrastructure.serialization import DomainEncoder


class PgOutboxRepository(OutboxRepository):
    """PostgreSQL-backed transactional outbox.

    Events are written to the outbox table in the SAME transaction
    as the business operation, guaranteeing at-least-once delivery.
    A separate worker polls for unsent events and publishes them.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def append(self, event: DomainEvent, aggregate_id: UUID) -> None:
        model = OutboxEventModel(
            aggregate_id=aggregate_id,
            event_type=event.event_type,
            payload=json.dumps(event.__dict__, cls=DomainEncoder),
        )
        self._session.add(model)
        await self._session.flush()

    async def get_pending(
        self, batch_size: int = 100
    ) -> list[dict[str, Any]]:
        stmt = (
            select(OutboxEventModel)
            .where(
                OutboxEventModel.sent.is_(False),
                OutboxEventModel.failed.is_(False),
            )
            .order_by(OutboxEventModel.created_at.asc())
            .limit(batch_size)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [
            {
                "id": m.id,
                "aggregate_id": m.aggregate_id,
                "event_type": m.event_type,
                "payload": m.payload,
                "created_at": m.created_at,
            }
            for m in models
        ]

    async def mark_sent(self, outbox_id: UUID) -> None:
        stmt = (
            update(OutboxEventModel)
            .where(OutboxEventModel.id == outbox_id)
            .values(sent=True)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def mark_failed(self, outbox_id: UUID, error: str) -> None:
        stmt = (
            update(OutboxEventModel)
            .where(OutboxEventModel.id == outbox_id)
            .values(failed=True, error=error)
        )
        await self._session.execute(stmt)
        await self._session.flush()
