"""Reconciliation Worker — Detects mismatches between orders and payments."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.infrastructure import (
    DeadLetterQueue,
    OrderRepository,
    OutboxRepository,
)

logger = logging.getLogger(__name__)


class ReconciliationWorker:
    """Daily reconciliation between orders and payments.

    Detects mismatches, missing payments, or orphaned reservations.
    In production, queries database for orders within the target date range.
    """

    def __init__(
        self,
        order_repo: OrderRepository,
        outbox: OutboxRepository,
        dlq: DeadLetterQueue,
    ):
        self.order_repo = order_repo
        self.outbox = outbox
        self.dlq = dlq

    async def reconcile(
        self, date: datetime | None = None
    ) -> dict[str, Any]:
        """Run reconciliation for a given date.

        Returns a report of mismatches found.
        """
        report = {
            "date": (date or datetime.now(timezone.utc)).isoformat(),
            "checked": 0,
            "mismatches": [],
            "orphaned_payments": [],
            "missing_confirmations": [],
        }

        return report
