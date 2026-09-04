"""Unit tests for Money value object."""
from decimal import Decimal

import pytest

from src.domain import Money


class TestMoney:
    def test_creation(self):
        m = Money(Decimal("10.50"))
        assert m.amount == Decimal("10.50")
        assert m.currency == "BRL"

    def test_addition(self):
        m1 = Money(Decimal("10.00"))
        m2 = Money(Decimal("5.50"))
        result = m1 + m2
        assert result.amount == Decimal("15.50")

    def test_multiplication(self):
        m = Money(Decimal("10.00"))
        result = m * 3
        assert result.amount == Decimal("30.00")

    def test_negative_amount_raises(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            Money(Decimal("-1.00"))

    def test_currency_mismatch_raises(self):
        m1 = Money(Decimal("10.00"), "BRL")
        m2 = Money(Decimal("5.00"), "USD")
        with pytest.raises(ValueError, match="Currency mismatch"):
            m1 + m2

    def test_frozen_immutability(self):
        m = Money(Decimal("10.00"))
        with pytest.raises(AttributeError):
            m.amount = Decimal("20.00")

    def test_invalid_currency_code_raises(self):
        with pytest.raises(ValueError, match="3-letter ISO"):
            Money(Decimal("10.00"), "US")

    def test_zero_amount_is_valid(self):
        m = Money(Decimal("0"))
        assert m.amount == Decimal("0")
