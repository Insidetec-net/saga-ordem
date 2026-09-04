"""Domain enumerations — State definitions for aggregates and processes."""
from enum import Enum, auto


class OrderStatus(Enum):
    """Order lifecycle states."""

    PENDING = auto()
    STOCK_RESERVED = auto()
    PAYMENT_PROCESSED = auto()
    CONFIRMED = auto()
    SHIPPED = auto()
    CANCELLED = auto()
    FAILED = auto()


class SagaState(Enum):
    """Saga orchestration states."""

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
    """Supported payment methods."""

    CREDIT_CARD = auto()
    PIX = auto()
    BOLETO = auto()


class StockOperation(Enum):
    """Stock mutation types."""

    RESERVE = auto()
    RELEASE = auto()
    CONFIRM = auto()
