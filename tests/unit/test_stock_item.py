"""Unit tests for StockItem aggregate."""
from uuid import uuid4

import pytest

from src.domain import InsufficientStock, StockItem


class TestStockItem:
    def test_reserve_decreases_effective(self):
        stock = StockItem(uuid4(), "Test", available_qty=10)
        stock.reserve(3)
        assert stock.reserved_qty == 3
        assert stock.effective_stock == 7

    def test_insufficient_stock_raises(self):
        stock = StockItem(uuid4(), "Test", available_qty=2)
        with pytest.raises(InsufficientStock):
            stock.reserve(5)

    def test_release_decreases_reserved(self):
        stock = StockItem(uuid4(), "Test", available_qty=10)
        stock.reserve(5)
        stock.release(2)
        assert stock.reserved_qty == 3

    def test_release_too_much_raises(self):
        stock = StockItem(uuid4(), "Test", available_qty=10)
        stock.reserve(3)
        with pytest.raises(Exception):
            stock.release(5)

    def test_confirm_reservation(self):
        stock = StockItem(uuid4(), "Test", available_qty=10)
        stock.reserve(4)
        stock.confirm_reservation(4)
        assert stock.reserved_qty == 0
        assert stock.available_qty == 6

    def test_reserve_zero_raises(self):
        stock = StockItem(uuid4(), "Test", available_qty=10)
        with pytest.raises(ValueError, match="positive"):
            stock.reserve(0)

    def test_reserve_negative_raises(self):
        stock = StockItem(uuid4(), "Test", available_qty=10)
        with pytest.raises(ValueError, match="positive"):
            stock.reserve(-1)

    def test_release_zero_raises(self):
        stock = StockItem(uuid4(), "Test", available_qty=10)
        stock.reserve(5)
        with pytest.raises(ValueError, match="positive"):
            stock.release(0)

    def test_effective_stock_calculation(self):
        stock = StockItem(uuid4(), "Test", available_qty=100, reserved_qty=30)
        assert stock.effective_stock == 70
