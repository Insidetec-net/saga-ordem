"""Tests — Unit, Integration, and Saga tests."""
from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from src.domain import (
    Address,
    InsufficientStock,
    InvalidStateTransition,
    Money,
    Order,
    OrderItem,
    OrderStatus,
    SagaState,
    StockItem,
)
from src.infrastructure import (
    DeadLetterQueue,
    InMemoryIdempotency,
    InMemoryOrderRepository,
    InMemoryOutbox,
    InMemorySagaLog,
    InMemoryStockRepository,
)
from src.application import OrderSagaOrchestrator, SagaExecutionError


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def order_repo():
    return InMemoryOrderRepository()


@pytest.fixture
def stock_repo():
    return InMemoryStockRepository()


@pytest.fixture
def outbox():
    return InMemoryOutbox()


@pytest.fixture
def idempotency():
    return InMemoryIdempotency()


@pytest.fixture
def saga_log():
    return InMemorySagaLog()


@pytest.fixture
def dlq():
    return DeadLetterQueue()


@pytest.fixture
def orchestrator(order_repo, stock_repo, outbox, idempotency, saga_log, dlq):
    return OrderSagaOrchestrator(
        order_repo=order_repo,
        stock_repo=stock_repo,
        outbox=outbox,
        idempotency=idempotency,
        saga_log=saga_log,
        dlq=dlq,
    )


@pytest.fixture
def sample_order():
    return Order(
        order_id=uuid4(),
        customer_id=uuid4(),
        items=[
            OrderItem(
                product_id=uuid4(),
                product_name="Product A",
                quantity=2,
                unit_price=Money(Decimal("50.00")),
            ),
            OrderItem(
                product_id=uuid4(),
                product_name="Product B",
                quantity=1,
                unit_price=Money(Decimal("100.00")),
            ),
        ],
    )


@pytest.fixture
def stocked_items(sample_order):
    """Stock items matching the sample order."""
    return [
        StockItem(
            product_id=sample_order.items[0].product_id,
            product_name="Product A",
            available_qty=10,
        ),
        StockItem(
            product_id=sample_order.items[1].product_id,
            product_name="Product B",
            available_qty=5,
        ),
    ]


# ═══════════════════════════════════════════════════════════════
# Domain Unit Tests
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# Saga Integration Tests
# ═══════════════════════════════════════════════════════════════

class TestSagaOrchestrator:
    @pytest.mark.asyncio
    async def test_full_saga_success(
        self, orchestrator, sample_order, stocked_items, stock_repo, order_repo
    ):
        """Test complete saga execution — all steps succeed."""
        for item in stocked_items:
            await stock_repo.seed(item)

        result = await orchestrator.execute(sample_order)

        assert result.status == OrderStatus.CONFIRMED
        assert result.total.amount == Decimal("200.00")

        # Verify stock was reserved
        stock_a = await stock_repo.get_by_product(sample_order.items[0].product_id)
        assert stock_a.reserved_qty == 2

    @pytest.mark.asyncio
    async def test_saga_compensates_on_insufficient_stock(
        self, orchestrator, sample_order, stock_repo, order_repo, dlq
    ):
        """Test compensation when stock is insufficient."""
        # Seed with insufficient stock
        await stock_repo.seed(StockItem(
            product_id=sample_order.items[0].product_id,
            product_name="Product A",
            available_qty=1,  # Need 2
        ))
        await stock_repo.seed(StockItem(
            product_id=sample_order.items[1].product_id,
            product_name="Product B",
            available_qty=5,
        ))

        with pytest.raises(SagaExecutionError):
            await orchestrator.execute(sample_order)

        # Verify order was cancelled
        saved_order = await order_repo.get_by_id(sample_order.order_id)
        assert saved_order.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_idempotency_returns_cached_on_completed(
        self, orchestrator, sample_order, stocked_items, stock_repo
    ):
        """Test that a second call returns the cached completed result."""
        for item in stocked_items:
            await stock_repo.seed(item)

        key = "unique-key-123"
        result1 = await orchestrator.execute(sample_order, idempotency_key=key)

        # Second call with same key should return the same order (not raise)
        result2 = await orchestrator.execute(sample_order, idempotency_key=key)
        assert result2.order_id == result1.order_id
        assert result2.status == OrderStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_idempotency_rejects_in_progress(
        self, orchestrator, sample_order, stocked_items, stock_repo, idempotency
    ):
        """Test that concurrent calls with same key are rejected while in progress."""
        # Manually set key to "processing" state
        await idempotency.check_and_store("in-progress-key")

        with pytest.raises(SagaExecutionError, match="already in progress"):
            await orchestrator.execute(sample_order, idempotency_key="in-progress-key")

    @pytest.mark.asyncio
    async def test_saga_logs_each_step(
        self, orchestrator, sample_order, stocked_items, stock_repo, saga_log
    ):
        """Test that saga logs all steps."""
        for item in stocked_items:
            await stock_repo.seed(item)

        await orchestrator.execute(sample_order)

        # Check that saga logs were created
        # (saga_id is generated internally, so we check by order_id)
        all_logs = [l for l in saga_log._logs if l["order_id"] == sample_order.order_id]
        step_names = [l["step_name"] for l in all_logs]

        assert "create_order" in step_names
        assert "reserve_stock" in step_names
        assert "process_payment" in step_names
        assert "confirm_order" in step_names

    @pytest.mark.asyncio
    async def test_outbox_receives_events(
        self, orchestrator, sample_order, stocked_items, stock_repo, outbox
    ):
        """Test that outbox captures all domain events."""
        for item in stocked_items:
            await stock_repo.seed(item)

        await orchestrator.execute(sample_order)

        pending = await outbox.get_pending()
        event_types = [p["event_type"] for p in pending]

        assert "OrderCreated" in event_types
        assert "StockReserved" in event_types
        assert "PaymentProcessed" in event_types
        assert "OrderConfirmed" in event_types


# ═══════════════════════════════════════════════════════════════
# Concurrency Tests
# ═══════════════════════════════════════════════════════════════

class TestConcurrency:
    @pytest.mark.asyncio
    async def test_optimistic_lock_prevents_lost_update(self, stock_repo):
        """Test that concurrent updates are detected."""
        product_id = uuid4()
        stock = StockItem(product_id, "Test", available_qty=10)
        await stock_repo.seed(stock)

        # First reservation succeeds
        s1 = await stock_repo.get_by_product(product_id)
        s1.reserve(3)
        success1 = await stock_repo.update_with_version(s1, 0)
        assert success1 is True

        # Second reservation with stale version fails
        s2 = await stock_repo.get_by_product(product_id)
        s2.reserve(3)
        success2 = await stock_repo.update_with_version(s2, 0)  # Stale version
        assert success2 is False

    @pytest.mark.asyncio
    async def test_concurrent_orders_on_same_stock(
        self, orchestrator, sample_order, stocked_items, stock_repo
    ):
        """Test two orders competing for the same stock."""
        # Only enough for one order
        await stock_repo.seed(StockItem(
            product_id=sample_order.items[0].product_id,
            product_name="Product A",
            available_qty=2,  # Exactly enough for one order
        ))
        await stock_repo.seed(StockItem(
            product_id=sample_order.items[1].product_id,
            product_name="Product B",
            available_qty=5,
        ))

        # First order succeeds
        order1 = Order(
            order_id=uuid4(),
            customer_id=sample_order.customer_id,
            items=sample_order.items,
        )
        result1 = await orchestrator.execute(order1, idempotency_key="order-1")
        assert result1.status == OrderStatus.CONFIRMED

        # Second order should fail (insufficient stock)
        order2 = Order(
            order_id=uuid4(),
            customer_id=sample_order.customer_id,
            items=sample_order.items,
        )
        with pytest.raises(SagaExecutionError):
            await orchestrator.execute(order2, idempotency_key="order-2")


# ═══════════════════════════════════════════════════════════════
# DLQ Tests
# ═══════════════════════════════════════════════════════════════

class TestDeadLetterQueue:
    @pytest.mark.asyncio
    async def test_dlq_captures_failed_events(self, dlq):
        await dlq.enqueue(
            event_type="test_event",
            payload={"data": "test"},
            error="Connection timeout",
        )
        assert dlq.size == 1

        messages = await dlq.get_all()
        assert messages[0]["event_type"] == "test_event"
        assert messages[0]["error"] == "Connection timeout"

    @pytest.mark.asyncio
    async def test_dlq_tracks_retry_count(self, dlq):
        await dlq.enqueue(
            event_type="test_event",
            payload={},
            error="Timeout",
            retry_count=3,
        )
        messages = await dlq.get_all()
        assert messages[0]["retry_count"] == 3
