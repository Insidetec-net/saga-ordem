"""PostgreSQL Saga Log — Persistent audit trail for saga execution."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain import SagaState
from src.infrastructure.database.models import SagaLogModel
from src.infrastructure.saga import SagaLogRepository


class PgSagaLog(SagaLogRepository):
    """PostgreSQL-backed saga execution log.

    Stores every step transition for auditing, debugging,
    and potential saga recovery after crashes.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def log_step(
        self,
        order_id: UUID,
        saga_id: UUID,
        step_name: str,
        state: SagaState,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        model = SagaLogModel(
            order_id=order_id,
            saga_id=saga_id,
            step_name=step_name,
            state=state.name,
            payload=json.dumps(payload) if payload else None,
            error=error,
        )
        self._session.add(model)
        await self._session.flush()

    async def get_saga_history(
        self, saga_id: UUID
    ) -> list[dict[str, Any]]:
        stmt = (
            select(SagaLogModel)
            .where(SagaLogModel.saga_id == saga_id)
            .order_by(SagaLogModel.created_at.asc())
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [
            {
                "id": m.id,
                "order_id": m.order_id,
                "saga_id": m.saga_id,
                "step_name": m.step_name,
                "state": m.state,
                "payload": m.payload,
                "error": m.error,
                "created_at": m.created_at,
            }
            for m in models
        ]
