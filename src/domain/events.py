"""Domain Events — Immutable records of things that happened in the domain."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4


@dataclass
class DomainEvent:
    """Base class for all domain events.

    Every event gets a unique ID and a UTC timestamp automatically.
    The event_type defaults to the class name if not provided.
    """

    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = ""

    def __post_init__(self):
        if not self.event_type:
            self.event_type = self.__class__.__name__


@dataclass
class OrderCreated(DomainEvent):
    order_id: UUID = field(default_factory=uuid4)
    customer_id: UUID = field(default_factory=uuid4)
    total: Decimal = Decimal("0")


@dataclass
class StockReserved(DomainEvent):
    order_id: UUID = field(default_factory=uuid4)
    items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class StockReservationFailed(DomainEvent):
    order_id: UUID = field(default_factory=uuid4)
    product_id: UUID = field(default_factory=uuid4)
    reason: str = ""


@dataclass
class StockReleased(DomainEvent):
    order_id: UUID = field(default_factory=uuid4)
    items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PaymentProcessed(DomainEvent):
    order_id: UUID = field(default_factory=uuid4)
    payment_id: UUID = field(default_factory=uuid4)
    amount: Decimal = Decimal("0")


@dataclass
class PaymentFailed(DomainEvent):
    order_id: UUID = field(default_factory=uuid4)
    reason: str = ""


@dataclass
class PaymentRefunded(DomainEvent):
    order_id: UUID = field(default_factory=uuid4)
    payment_id: UUID = field(default_factory=uuid4)
    amount: Decimal = Decimal("0")


@dataclass
class OrderConfirmed(DomainEvent):
    order_id: UUID = field(default_factory=uuid4)
    confirmed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class OrderCancelled(DomainEvent):
    order_id: UUID = field(default_factory=uuid4)
    reason: str = ""


@dataclass
class SagaFailed(DomainEvent):
    order_id: UUID = field(default_factory=uuid4)
    failed_step: str = ""
    reason: str = ""
