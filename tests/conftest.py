"""Shared test fixtures for all test modules."""
from __future__ import annotations

import pytest
from decimal import Decimal
from uuid import uuid4

from src.domain import Money, Order, OrderItem, StockItem
from src.infrastructure import (
    DeadLetterQueue,
    InMemoryIdempotency,
    InMemoryOrderRepository,
    InMemoryOutbox,
    InMemorySagaLog,
    InMemoryStockRepository,
)
from src.application import OrderSagaOrchestrator


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
