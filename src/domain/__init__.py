"""Domain layer — Aggregates, entities, value objects, and domain events."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum, auto
from typing import Any
from uuid import UUID, uuid4


# ═══════════════════════════════════════════════════════════════
# Value Objects
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "BRL"

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("Money amount cannot be negative")
        if len(self.currency) != 3:
            raise ValueError("Currency must be 3-letter ISO code")

    def __add__(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __mul__(self, qty: int) -> Money:
        return Money(self.amount * qty, self.currency)

    def _check_currency(self, other: Money):
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} vs {other.currency}")


@dataclass(frozen=True)
class Address:
    street: str
    city: str
    state: str
    zip_code: str
    country: str = "BR"


# ═══════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════

class OrderStatus(Enum):
    PENDING = auto()
    STOCK_RESERVED = auto()
    PAYMENT_PROCESSED = auto()
    CONFIRMED = auto()
    SHIPPED = auto()
    CANCELLED = auto()
    FAILED = auto()


class SagaState(Enum):
    STARTED = auto()
    STOCK_RESERVING = auto()
    STOCK_RESERVED = auto()
    PAYMENT_PROCESSING = auto()
    PAYMENT_COMPLETED = auto()
    COMPLETING = auto()
    COMPLETED = auto()
    COMPENSATING = auto()
    FAILED = auto()


class PaymentMethod(Enum):
    CREDIT_CARD = auto()
    PIX = auto()
    BOLETO = auto()


class StockOperation(Enum):
    RESERVE = auto()
    RELEASE = auto()
    CONFIRM = auto()


# ═══════════════════════════════════════════════════════════════
# Domain Events
# ═══════════════════════════════════════════════════════════════

@dataclass
class DomainEvent:
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


# ═══════════════════════════════════════════════════════════════
# Aggregates
# ═══════════════════════════════════════════════════════════════

@dataclass
class OrderItem:
    product_id: UUID
    product_name: str
    quantity: int
    unit_price: Money
    version: int = 0  # Optimistic locking

    @property
    def subtotal(self) -> Money:
        return self.unit_price * self.quantity


@dataclass
class Order:
    order_id: UUID
    customer_id: UUID
    items: list[OrderItem]
    status: OrderStatus = OrderStatus.PENDING
    shipping_address: Address | None = None
    payment_method: PaymentMethod = PaymentMethod.PIX
    total: Money = field(default_factory=lambda: Money(Decimal("0")))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 0
    events: list[DomainEvent] = field(default_factory=list)

    def __post_init__(self):
        if self.total.amount == 0:
            self.total = self._calculate_total()

    def _calculate_total(self) -> Money:
        if not self.items:
            return Money(Decimal("0"))
        total = self.items[0].subtotal
        for item in self.items[1:]:
            total += item.subtotal
        return total

    def reserve_stock(self) -> list[StockReserved]:
        """Transition to STOCK_RESERVED, emit event."""
        if self.status != OrderStatus.PENDING:
            raise InvalidStateTransition(
                f"Cannot reserve stock from status {self.status.name}"
            )
        self.status = OrderStatus.STOCK_RESERVED
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        event = StockReserved(
            order_id=self.order_id,
            items=[{"product_id": str(i.product_id), "qty": i.quantity} for i in self.items]
        )
        self.events.append(event)
        return [event]

    def process_payment(self) -> list[PaymentProcessed]:
        """Transition to PAYMENT_PROCESSED, emit event."""
        if self.status != OrderStatus.STOCK_RESERVED:
            raise InvalidStateTransition(
                f"Cannot process payment from status {self.status.name}"
            )
        self.status = OrderStatus.PAYMENT_PROCESSED
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        event = PaymentProcessed(
            order_id=self.order_id,
            amount=self.total.amount
        )
        self.events.append(event)
        return [event]

    def confirm(self) -> list[OrderConfirmed]:
        """Final confirmation, order is live."""
        if self.status != OrderStatus.PAYMENT_PROCESSED:
            raise InvalidStateTransition(
                f"Cannot confirm from status {self.status.name}"
            )
        self.status = OrderStatus.CONFIRMED
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        event = OrderConfirmed(order_id=self.order_id)
        self.events.append(event)
        return [event]

    def cancel(self, reason: str = "") -> list[OrderCancelled]:
        """Cancel the order."""
        if self.status in (OrderStatus.SHIPPED, OrderStatus.CONFIRMED):
            raise InvalidStateTransition(
                f"Cannot cancel order in {self.status.name}"
            )
        self.status = OrderStatus.CANCELLED
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        event = OrderCancelled(order_id=self.order_id, reason=reason)
        self.events.append(event)
        return [event]

    def mark_failed(self, reason: str = "") -> list[SagaFailed]:
        """Mark order as failed."""
        self.status = OrderStatus.FAILED
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        event = SagaFailed(order_id=self.order_id, reason=reason)
        self.events.append(event)
        return [event]

    def clear_events(self):
        self.events.clear()


@dataclass
class StockItem:
    product_id: UUID
    product_name: str
    available_qty: int
    reserved_qty: int = 0
    version: int = 0

    @property
    def effective_stock(self) -> int:
        return self.available_qty - self.reserved_qty

    def reserve(self, qty: int) -> None:
        """Reserve stock with optimistic locking check."""
        if qty <= 0:
            raise ValueError("Quantity must be positive")
        if self.effective_stock < qty:
            raise InsufficientStock(
                f"Product {self.product_id}: requested {qty}, available {self.effective_stock}"
            )
        self.reserved_qty += qty

    def release(self, qty: int) -> None:
        """Release reserved stock (compensating action)."""
        if qty <= 0:
            raise ValueError("Quantity must be positive")
        if self.reserved_qty < qty:
            raise InvalidStockOperation(
                f"Cannot release {qty}, only {self.reserved_qty} reserved"
            )
        self.reserved_qty -= qty

    def confirm_reservation(self, qty: int) -> None:
        """Move reserved to sold (decrease available)."""
        if self.reserved_qty < qty:
            raise InvalidStockOperation(
                f"Cannot confirm {qty}, only {self.reserved_qty} reserved"
            )
        self.reserved_qty -= qty
        self.available_qty -= qty


# ═══════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════

class DomainError(Exception):
    """Base domain exception."""
    pass


class InvalidStateTransition(DomainError):
    """Attempted invalid state machine transition."""
    pass


class InsufficientStock(DomainError):
    """Not enough stock available."""
    pass


class InvalidStockOperation(DomainError):
    """Invalid stock operation."""
    pass


class DuplicateOrderError(DomainError):
    """Idempotency violation — order already exists."""
    pass


class SagaExecutionError(DomainError):
    """Saga step failed and compensation may be needed."""
    pass
