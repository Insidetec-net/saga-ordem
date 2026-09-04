"""Domain exceptions — Business rule violations."""


class DomainError(Exception):
    """Base domain exception."""

    pass

class ConcurrencyException(DomainError):
    """Optimistic locking collision."""

    pass


class InvalidStateTransition(DomainError):
    """Attempted invalid state machine transition."""

    pass


class InsufficientStock(DomainError):
    """Not enough stock available."""

    pass


class InvalidStockOperation(DomainError):
    """Invalid stock operation (e.g., releasing more than reserved)."""

    pass


class DuplicateOrderError(DomainError):
    """Idempotency violation — order already exists."""

    pass


class SagaExecutionError(DomainError):
    """Saga step failed and compensation may be needed."""

    pass
