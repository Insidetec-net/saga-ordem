"""Celery Worker Entrypoint."""
import asyncio
from celery import Celery
import redis.asyncio as redis

from src.config import settings
from src.infrastructure.database.connection import Database
from src.infrastructure.outbox.pg_outbox_repository import PgOutboxRepository
from src.infrastructure.dlq.pg_dlq import PgDLQ
from src.infrastructure.saga.pg_saga_log import PgSagaLog
from src.application.reconciliation import ReconciliationWorker
from src.infrastructure.repositories.pg_order_repository import PgOrderRepository
from src.infrastructure.repositories.pg_stock_repository import PgStockRepository

from src.workers import create_celery_app, register_tasks


def init_worker_app() -> Celery:
    """Initialize Celery with real infrastructure dependencies."""
    app = create_celery_app(settings.redis_url)

    # We use a trick to pass async dependencies to synchronous Celery tasks:
    # the task functions will create their own sessions using `Database.get_session_factory()`
    
    # Actually, we can just instantiate the DB factory here, and let tasks use it.
    db = Database(settings.database_url)
    session_factory = db.get_session_factory()

    # Create a global context object or just pass the factory to register_tasks
    register_tasks(app, session_factory)

    return app

# The Celery worker will look for `app` or `celery` in this module
celery_app = init_worker_app()
