"""Unit tests for Order aggregate."""
from decimal import Decimal
from uuid import uuid4

import pytest

from src.domain import (
    InvalidStateTransition,
    Money,
    Order,
    OrderItem,
    OrderStatus,
)


class TestOrderItem:
    def test_subtotal(self):
        item = OrderItem(
            product_id=uuid4(),
            product_name="Test",
            quantity=3,
            unit_price=Money(Decimal("10.00")),
        )
        assert item.subtotal.amount == Decimal("30.00")


class TestOrder:
    def test_total_calculation(self):
        order = Order(
            order_id=uuid4(),
            customer_id=uuid4(),
            items=[
                OrderItem(uuid4(), "A", 2, Money(Decimal("50.00"))),
                OrderItem(uuid4(), "B", 1, Money(Decimal("100.00"))),
            ],
        )
        assert order.total.amount == Decimal("200.00")

    def test_reserve_stock_transitions_state(self, sample_order):
        events = sample_order.reserve_stock()
        assert sample_order.status == OrderStatus.STOCK_RESERVED
        assert len(events) == 1
        assert events[0].event_type == "StockReserved"

    def test_process_payment_after_stock(self, sample_order):
        sample_order.reserve_stock()
        events = sample_order.process_payment()
        assert sample_order.status == OrderStatus.PAYMENT_PROCESSED
        assert len(events) == 1

    def test_confirm_order(self, sample_order):
        sample_order.reserve_stock()
        sample_order.process_payment()
        events = sample_order.confirm()
        assert sample_order.status == OrderStatus.CONFIRMED
        assert len(events) == 1

    def test_invalid_transition_raises(self, sample_order):
        with pytest.raises(InvalidStateTransition):
            sample_order.process_payment()

    def test_cancel_pending_order(self, sample_order):
        events = sample_order.cancel("Customer request")
        assert sample_order.status == OrderStatus.CANCELLED
        assert events[0].reason == "Customer request"

    def test_cannot_cancel_confirmed(self, sample_order):
        sample_order.reserve_stock()
        sample_order.process_payment()
        sample_order.confirm()
        with pytest.raises(InvalidStateTransition):
            sample_order.cancel()

    def test_version_increments_on_transitions(self, sample_order):
        assert sample_order.version == 0
        sample_order.reserve_stock()
        assert sample_order.version == 1
        sample_order.process_payment()
        assert sample_order.version == 2

    def test_clear_events(self, sample_order):
        sample_order.reserve_stock()
        assert len(sample_order.events) == 1
        sample_order.clear_events()
        assert len(sample_order.events) == 0

    def test_mark_failed(self, sample_order):
        events = sample_order.mark_failed("Gateway timeout")
        assert sample_order.status == OrderStatus.FAILED
        assert events[0].reason == "Gateway timeout"
