"""Domain layer — Public API.

Re-exports all domain types for convenient imports:
    from src.domain import Order, Money, OrderStatus, ...
"""

from .aggregates import Order, OrderItem, StockItem
from .enums import OrderStatus, PaymentMethod, SagaState, StockOperation
from .events import (
    DomainEvent,
    OrderCancelled,
    OrderConfirmed,
    OrderCreated,
    PaymentFailed,
    PaymentProcessed,
    PaymentRefunded,
    SagaFailed,
    StockReleased,
    StockReservationFailed,
    StockReserved,
)
from .exceptions import (
    DomainError,
    DuplicateOrderError,
    InsufficientStock,
    InvalidStateTransition,
    InvalidStockOperation,
    SagaExecutionError,
)
from .value_objects import Address, Money

__all__ = [
    # Value Objects
    "Address",
    "Money",
    # Enums
    "OrderStatus",
    "PaymentMethod",
    "SagaState",
    "StockOperation",
    # Aggregates
    "Order",
    "OrderItem",
    "StockItem",
    # Events
    "DomainEvent",
    "OrderCancelled",
    "OrderConfirmed",
    "OrderCreated",
    "PaymentFailed",
    "PaymentProcessed",
    "PaymentRefunded",
    "SagaFailed",
    "StockReleased",
    "StockReservationFailed",
    "StockReserved",
    # Exceptions
    "DomainError",
    "DuplicateOrderError",
    "InsufficientStock",
    "InvalidStateTransition",
    "InvalidStockOperation",
    "SagaExecutionError",
]
