"""Concurrency tests — optimistic locking and race conditions."""
from uuid import uuid4

import pytest

from src.domain import Order, OrderStatus, StockItem
from src.application import SagaExecutionError


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
        success2 = await stock_repo.update_with_version(s2, 0)  # Stale
        assert success2 is False

    @pytest.mark.asyncio
    async def test_concurrent_orders_on_same_stock(
        self, orchestrator, sample_order, stock_repo
    ):
        """Test two orders competing for the same stock."""
        # Only enough for one order
        await stock_repo.seed(
            StockItem(
                product_id=sample_order.items[0].product_id,
                product_name="Product A",
                available_qty=2,  # Exactly enough for one order
            )
        )
        await stock_repo.seed(
            StockItem(
                product_id=sample_order.items[1].product_id,
                product_name="Product B",
                available_qty=5,
            )
        )

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
