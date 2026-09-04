"""Infrastructure — Repositories, Outbox, Idempotency, Redis locking."""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from src.domain import (
    DomainEvent,
    Money,
    Order,
    OrderItem,
    OrderStatus,
    StockItem,
    SagaState,
    SagaExecutionError,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# JSON Encoder for domain objects
# ═══════════════════════════════════════════════════════════════

class DomainEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, Money):
            return {"amount": str(obj.amount), "currency": obj.currency}
        if isinstance(obj, DomainEvent):
            return obj.__dict__
        return super().default(obj)


def domain_hook(dct: dict) -> Any:
    """JSON object_hook to reconstruct domain events."""
    if "event_type" not in dct:
        return dct
    event_type = dct.pop("event_type")
    event_map = {
        "OrderCreated": "OrderCreated",
        "StockReserved": "StockReserved",
        "StockReservationFailed": "StockReservationFailed",
        "StockReleased": "StockReleased",
        "PaymentProcessed": "PaymentProcessed",
        "PaymentFailed": "PaymentFailed",
        "PaymentRefunded": "PaymentRefunded",
        "OrderConfirmed": "OrderConfirmed",
        "OrderCancelled": "OrderCancelled",
        "SagaFailed": "SagaFailed",
    }
    return dct  # Simplified — full reconstruction in event handler


# ═══════════════════════════════════════════════════════════════
# Repository Interfaces
# ═══════════════════════════════════════════════════════════════

class OrderRepository(ABC):
    @abstractmethod
    async def save(self, order: Order) -> None: ...

    @abstractmethod
    async def get_by_id(self, order_id: UUID) -> Order | None: ...

    @abstractmethod
    async def update(self, order: Order) -> None: ...

    @abstractmethod
    async def list_by_customer(self, customer_id: UUID, limit: int = 50) -> list[Order]: ...


class StockRepository(ABC):
    @abstractmethod
    async def get_by_product(self, product_id: UUID) -> StockItem | None: ...

    @abstractmethod
    async def save(self, item: StockItem) -> None: ...

    @abstractmethod
    async def update_with_version(self, item: StockItem, expected_version: int) -> bool:
        """Optimistic lock update. Returns False if version mismatch."""
        ...


class OutboxRepository(ABC):
    @abstractmethod
    async def append(self, event: DomainEvent, aggregate_id: UUID) -> None: ...

    @abstractmethod
    async def get_pending(self, batch_size: int = 100) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def mark_sent(self, outbox_id: UUID) -> None: ...

    @abstractmethod
    async def mark_failed(self, outbox_id: UUID, error: str) -> None: ...


class IdempotencyStore(ABC):
    @abstractmethod
    async def check_and_store(self, key: str, ttl_seconds: int = 86400) -> bool:
        """Returns True if new (stored), False if duplicate."""
        ...

    @abstractmethod
    async def get_result(self, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def store_result(self, key: str, result: dict[str, Any], ttl_seconds: int = 86400) -> None: ...


class SagaLogRepository(ABC):
    @abstractmethod
    async def log_step(
        self,
        order_id: UUID,
        saga_id: UUID,
        step_name: str,
        state: SagaState,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None: ...

    @abstractmethod
    async def get_saga_history(self, saga_id: UUID) -> list[dict[str, Any]]: ...


# ═══════════════════════════════════════════════════════════════
# In-Memory Implementations (for tests / demo)
# ═══════════════════════════════════════════════════════════════

class InMemoryOrderRepository(OrderRepository):
    def __init__(self):
        self._orders: dict[UUID, Order] = {}

    async def save(self, order: Order) -> None:
        self._orders[order.order_id] = order

    async def get_by_id(self, order_id: UUID) -> Order | None:
        return self._orders.get(order_id)

    async def update(self, order: Order) -> None:
        if order.order_id not in self._orders:
            raise ValueError(f"Order {order.order_id} not found")
        self._orders[order.order_id] = order

    async def list_by_customer(self, customer_id: UUID, limit: int = 50) -> list[Order]:
        return [
            o for o in self._orders.values()
            if o.customer_id == customer_id
        ][:limit]


class InMemoryStockRepository(StockRepository):
    def __init__(self):
        self._stock: dict[UUID, StockItem] = {}

    async def seed(self, item: StockItem) -> None:
        self._stock[item.product_id] = item

    async def get_by_product(self, product_id: UUID) -> StockItem | None:
        return self._stock.get(product_id)

    async def save(self, item: StockItem) -> None:
        self._stock[item.product_id] = item

    async def update_with_version(self, item: StockItem, expected_version: int) -> bool:
        current = self._stock.get(item.product_id)
        if current is None or current.version != expected_version:
            return False
        item.version = current.version + 1
        self._stock[item.product_id] = item
        return True


class InMemoryOutbox(OutboxRepository):
    def __init__(self):
        self._messages: list[dict[str, Any]] = []

    async def append(self, event: DomainEvent, aggregate_id: UUID) -> None:
        self._messages.append({
            "id": uuid4(),
            "aggregate_id": aggregate_id,
            "event_type": event.event_type,
            "payload": json.dumps(event.__dict__, cls=DomainEncoder),
            "created_at": datetime.now(timezone.utc),
            "sent": False,
            "failed": False,
        })

    async def get_pending(self, batch_size: int = 100) -> list[dict[str, Any]]:
        return [m for m in self._messages if not m["sent"] and not m["failed"]][:batch_size]

    async def mark_sent(self, outbox_id: UUID) -> None:
        for m in self._messages:
            if m["id"] == outbox_id:
                m["sent"] = True

    async def mark_failed(self, outbox_id: UUID, error: str) -> None:
        for m in self._messages:
            if m["id"] == outbox_id:
                m["failed"] = True
                m["error"] = error


class InMemoryIdempotency(IdempotencyStore):
    def __init__(self):
        self._store: dict[str, Any] = {}

    async def check_and_store(self, key: str, ttl_seconds: int = 86400) -> bool:
        if key in self._store:
            return False
        self._store[key] = {"status": "processing"}
        return True

    async def get_result(self, key: str) -> dict[str, Any] | None:
        return self._store.get(key)

    async def store_result(self, key: str, result: dict[str, Any], ttl_seconds: int = 86400) -> None:
        self._store[key] = result


class InMemorySagaLog(SagaLogRepository):
    def __init__(self):
        self._logs: list[dict[str, Any]] = []

    async def log_step(
        self,
        order_id: UUID,
        saga_id: UUID,
        step_name: str,
        state: SagaState,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self._logs.append({
            "id": uuid4(),
            "order_id": order_id,
            "saga_id": saga_id,
            "step_name": step_name,
            "state": state.name,
            "payload": payload,
            "error": error,
            "created_at": datetime.now(timezone.utc),
        })

    async def get_saga_history(self, saga_id: UUID) -> list[dict[str, Any]]:
        return [l for l in self._logs if l["saga_id"] == saga_id]


# ═══════════════════════════════════════════════════════════════
# Redis-based Idempotency (production)
# ═══════════════════════════════════════════════════════════════

class RedisIdempotency(IdempotencyStore):
    """Idempotency check using Redis SET NX (set-if-not-exists)."""

    def __init__(self, redis_client):
        self._redis = redis_client
        self.prefix = "idempotency:"

    async def check_and_store(self, key: str, ttl_seconds: int = 86400) -> bool:
        full_key = f"{self.prefix}{key}"
        # SET NX returns True if set (new), None if exists (duplicate)
        result = await self._redis.set(full_key, "processing", nx=True, ex=ttl_seconds)
        return result is True

    async def get_result(self, key: str) -> dict[str, Any] | None:
        full_key = f"{self.prefix}{key}"
        data = await self._redis.get(full_key)
        if data is None:
            return None
        return json.loads(data)

    async def store_result(self, key: str, result: dict[str, Any], ttl_seconds: int = 86400) -> None:
        full_key = f"{self.prefix}{key}"
        await self._redis.set(full_key, json.dumps(result, cls=DomainEncoder), ex=ttl_seconds)


# ═══════════════════════════════════════════════════════════════
# Dead Letter Queue
# ═══════════════════════════════════════════════════════════════

class DeadLetterQueue:
    """Captures failed events for later inspection and retry."""

    def __init__(self):
        self._messages: list[dict[str, Any]] = []

    async def enqueue(
        self,
        event_type: str,
        payload: dict[str, Any],
        error: str,
        retry_count: int = 0,
    ) -> None:
        self._messages.append({
            "id": uuid4(),
            "event_type": event_type,
            "payload": payload,
            "error": error,
            "retry_count": retry_count,
            "created_at": datetime.now(timezone.utc),
        })
        logger.error(f"DLQ: {event_type} failed — {error}")

    @property
    def size(self) -> int:
        return len(self._messages)

    async def get_all(self) -> list[dict[str, Any]]:
        return list(self._messages)
