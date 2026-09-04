"""Infrastructure layer — Public API.

Re-exports all infrastructure types for convenient imports:
    from src.infrastructure import InMemoryOrderRepository, ...
"""

import json

from .dlq import DeadLetterQueue
from .idempotency import (
    IdempotencyStore,
    InMemoryIdempotency,
    RedisIdempotency,
)
from .outbox import InMemoryOutbox, OutboxRepository
from .repositories import (
    InMemoryOrderRepository,
    InMemoryStockRepository,
    OrderRepository,
    StockRepository,
)
from .saga import InMemorySagaLog, SagaLogRepository
from .serialization import DomainEncoder, domain_hook

__all__ = [
    # Repositories
    "OrderRepository",
    "InMemoryOrderRepository",
    "StockRepository",
    "InMemoryStockRepository",
    # Outbox
    "OutboxRepository",
    "InMemoryOutbox",
    # Idempotency
    "IdempotencyStore",
    "InMemoryIdempotency",
    "RedisIdempotency",
    # Saga Log
    "SagaLogRepository",
    "InMemorySagaLog",
    # DLQ
    "DeadLetterQueue",
    # Serialization
    "DomainEncoder",
    "domain_hook",
    "json",
]
