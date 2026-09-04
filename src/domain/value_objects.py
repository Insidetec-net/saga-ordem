"""Value Objects — Immutable objects defined by their attributes, not identity."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Money:
    """Monetary value with currency.

    Enforces non-negative amounts and currency consistency on arithmetic.
    Uses Decimal to avoid floating-point precision issues.
    """

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
    """Shipping address value object."""

    street: str
    city: str
    state: str
    zip_code: str
    country: str = "BR"
