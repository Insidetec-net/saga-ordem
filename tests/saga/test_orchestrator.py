"""Saga orchestrator integration tests — full saga flow."""
from decimal import Decimal

import pytest

from src.domain import OrderStatus, StockItem
from src.application import SagaExecutionError


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
        stock_a = await stock_repo.get_by_product(
            sample_order.items[0].product_id
        )
        assert stock_a.reserved_qty == 2

    @pytest.mark.asyncio
    async def test_saga_logs_each_step(
        self, orchestrator, sample_order, stocked_items, stock_repo, saga_log
    ):
        """Test that saga logs all steps."""
        for item in stocked_items:
            await stock_repo.seed(item)

        await orchestrator.execute(sample_order)

        all_logs = [
            entry
            for entry in saga_log._logs
            if entry["order_id"] == sample_order.order_id
        ]
        step_names = [entry["step_name"] for entry in all_logs]

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
