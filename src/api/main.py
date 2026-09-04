"""API entry point — Application factory with dependency wiring."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from src.config import settings
from src.infrastructure import (
    DeadLetterQueue,
    InMemoryIdempotency,
    InMemoryOutbox,
    InMemorySagaLog,
)
from src.infrastructure.database.connection import async_session_factory, engine
from src.infrastructure.database.models import Base
from src.infrastructure.repositories.pg_order_repository import PgOrderRepository
from src.infrastructure.repositories.pg_stock_repository import PgStockRepository
from src.infrastructure.outbox.pg_outbox_repository import PgOutboxRepository
from src.infrastructure.saga.pg_saga_log import PgSagaLog
from src.infrastructure.idempotency.redis_idempotency import RedisIdempotency

from src.application import OrderSagaOrchestrator
from src.application.reconciliation import ReconciliationWorker

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    """Application startup and shutdown events."""
    logger.info("Starting Order Saga API...")

    # Create tables if they don't exist (dev only — use Alembic in prod)
    if settings.app_debug:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified")

    yield

    # Shutdown
    await engine.dispose()
    logger.info("Order Saga API shutdown complete")


def create_configured_app():
    """Create FastAPI app with production dependencies."""
    from src.api import create_app

    # For now, use in-memory for idempotency, outbox, saga_log, dlq
    # These will be swapped to PG/Redis implementations per-request
    # via FastAPI dependency injection

    dlq = DeadLetterQueue()

    # We create a "factory orchestrator" that uses per-request sessions
    # The actual DI happens via the endpoint dependencies below
    from fastapi import Depends, FastAPI

    base_app = FastAPI(
        title="Order Processing System — Saga Pattern",
        description=(
            "Production-grade order processing demonstrating "
            "Saga Orchestration, Outbox Pattern, idempotency, "
            "and optimistic concurrency control."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # ── Dependency injection ─────────────────────────────────

    async def get_db_session():
        async with async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def get_orchestrator(session=Depends(get_db_session)):
        order_repo = PgOrderRepository(session)
        stock_repo = PgStockRepository(session)
        outbox = PgOutboxRepository(session)
        
        # Redis client shared across requests (instantiated ideally on startup, but OK here for DI logic)
        import redis.asyncio as redis
        redis_client = redis.from_url(settings.redis_url)
        idempotency = RedisIdempotency(redis_client)
        
        saga_log = PgSagaLog(session)

        return OrderSagaOrchestrator(
            order_repo=order_repo,
            stock_repo=stock_repo,
            outbox=outbox,
            idempotency=idempotency,
            saga_log=saga_log,
            dlq=dlq,
        )

    # ── Routes ───────────────────────────────────────────────

    # Routes are now registered via routers below

    @base_app.get("/health")
    async def health_check():
        return {"status": "ok"}

    from fastapi import Request
    from fastapi.responses import JSONResponse
    from src.domain.exceptions import DomainError, ConcurrencyException

    @base_app.exception_handler(DomainError)
    async def domain_exception_handler(request: Request, exc: DomainError):
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @base_app.exception_handler(ConcurrencyException)
    async def concurrency_exception_handler(request: Request, exc: ConcurrencyException):
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    from src.api.routers.orders import router as orders_router, get_orchestrator_stub
    base_app.include_router(orders_router)

    # Set up dependency injection for the orchestrator
    base_app.dependency_overrides[get_orchestrator_stub] = get_orchestrator

    return base_app


# Application instance
app = create_configured_app()
