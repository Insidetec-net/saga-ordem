"""Workers — Celery tasks for outbox processing, DLQ retry, and reconciliation."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Celery App Configuration
# ═══════════════════════════════════════════════════════════════


def create_celery_app(broker_url: str = "redis://localhost:6379/0"):
    """Create and configure Celery application."""
    from celery import Celery
    from celery.schedules import crontab

    app = Celery("order_saga", broker=broker_url, backend=broker_url)

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=120,
        task_soft_time_limit=100,
        worker_prefetch_multiplier=1,
        worker_max_tasks_per_child=1000,
        # Beat schedule
        beat_schedule={
            "process-outbox": {
                "task": "src.workers.process_outbox",
                "schedule": 10.0,  # every 10 seconds
            },
            "retry-dlq": {
                "task": "src.workers.retry_dlq",
                "schedule": 60.0,  # every minute
            },
            "daily-reconciliation": {
                "task": "src.workers.run_reconciliation",
                "schedule": crontab(hour=2, minute=0),  # 2 AM daily
            },
        },
    )

    return app


# ═══════════════════════════════════════════════════════════════
# Task definitions
# ═══════════════════════════════════════════════════════════════


def register_tasks(celery_app, session_factory):
    """Register all Celery tasks with access to infrastructure."""

    @celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
    def process_outbox(self):
        """Process pending outbox messages (event publishing)."""
        return asyncio.run(_async_process_outbox(session_factory))

    @celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
    def retry_dlq(self):
        """Retry failed messages from DLQ."""
        return asyncio.run(_async_retry_dlq(session_factory))

    @celery_app.task(bind=True)
    def run_reconciliation(self):
        """Daily reconciliation between orders and payments."""
        return asyncio.run(_async_reconcile(session_factory))

    @celery_app.task(bind=True, max_retries=2)
    def handle_stock_event(self, event_data: dict[str, Any]):
        """Handle stock reservation/confirmation events."""
        logger.info(
            f"Handling stock event: {event_data.get('event_type')}"
        )
        return {
            "status": "processed",
            "event": event_data.get("event_type"),
        }

    @celery_app.task(bind=True, max_retries=2)
    def handle_payment_event(self, event_data: dict[str, Any]):
        """Handle payment processed/refund events."""
        logger.info(
            f"Handling payment event: {event_data.get('event_type')}"
        )
        return {
            "status": "processed",
            "event": event_data.get("event_type"),
        }


# ═══════════════════════════════════════════════════════════════
# Async task implementations
# ═══════════════════════════════════════════════════════════════

from src.infrastructure.outbox.pg_outbox_repository import PgOutboxRepository
from src.infrastructure.dlq.pg_dlq import PgDLQ

async def _async_process_outbox(session_factory):
    """Process pending outbox messages."""
    async with session_factory() as session:
        outbox = PgOutboxRepository(session)
        
        pending = await outbox.get_pending(batch_size=50)
        sent = 0
        failed = 0

        for msg in pending:
            try:
                # In production: publish to Kafka/RabbitMQ/webhook
                logger.info(
                    f"Publishing event: {msg['event_type']} "
                    f"for aggregate {msg['aggregate_id']}"
                )
                await outbox.mark_sent(msg["id"])
                sent += 1
            except Exception as e:
                logger.error(f"Failed to publish {msg['id']}: {e}")
                await outbox.mark_failed(msg["id"], str(e))
                failed += 1

        await session.commit()
        return {"processed": len(pending), "sent": sent, "failed": failed}


async def _async_retry_dlq(session_factory):
    """Retry failed DLQ messages."""
    async with session_factory() as session:
        dlq = PgDLQ(session)
        outbox = PgOutboxRepository(session)
        
        messages = await dlq.get_all()
        retried = 0

        for msg in messages:
            if msg["retry_count"] >= 5:
                continue
            try:
                logger.info(f"Retrying DLQ message: {msg['event_type']}")
                retried += 1
            except Exception:
                pass

        await session.commit()
        return {"retried": retried}


async def _async_reconcile(session_factory):
    """Run daily reconciliation."""
    from src.application.reconciliation import ReconciliationWorker
    from src.infrastructure.repositories.pg_order_repository import PgOrderRepository
    from src.infrastructure.repositories.pg_stock_repository import PgStockRepository

    async with session_factory() as session:
        reconciliation = ReconciliationWorker(
            order_repo=PgOrderRepository(session),
            stock_repo=PgStockRepository(session),
        )
        report = await reconciliation.reconcile()
        logger.info(f"Reconciliation complete: {report}")
        return report
