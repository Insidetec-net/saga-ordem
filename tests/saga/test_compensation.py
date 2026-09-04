"""Saga compensation tests — verify rollback on failure."""
import pytest

from src.domain import OrderStatus, StockItem
from src.application import SagaExecutionError


class TestSagaCompensation:
    @pytest.mark.asyncio
    async def test_saga_compensates_on_insufficient_stock(
        self, orchestrator, sample_order, stock_repo, order_repo, dlq
    ):
        """Test compensation when stock is insufficient."""
        # Seed with insufficient stock
        await stock_repo.seed(
            StockItem(
                product_id=sample_order.items[0].product_id,
                product_name="Product A",
                available_qty=1,  # Need 2
            )
        )
        await stock_repo.seed(
            StockItem(
                product_id=sample_order.items[1].product_id,
                product_name="Product B",
                available_qty=5,
            )
        )

        with pytest.raises(SagaExecutionError):
            await orchestrator.execute(sample_order)

        # Verify order was cancelled via compensation
        saved_order = await order_repo.get_by_id(sample_order.order_id)
        assert saved_order.status == OrderStatus.CANCELLED
