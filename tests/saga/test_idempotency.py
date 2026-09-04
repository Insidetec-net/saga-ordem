"""Saga idempotency tests — verify duplicate request handling."""
import pytest

from src.domain import OrderStatus
from src.application import SagaExecutionError


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_idempotency_returns_cached_on_completed(
        self, orchestrator, sample_order, stocked_items, stock_repo
    ):
        """Test that a second call returns the cached completed result."""
        for item in stocked_items:
            await stock_repo.seed(item)

        key = "unique-key-123"
        result1 = await orchestrator.execute(
            sample_order, idempotency_key=key
        )

        # Second call with same key should return the same order
        result2 = await orchestrator.execute(
            sample_order, idempotency_key=key
        )
        assert result2.order_id == result1.order_id
        assert result2.status == OrderStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_idempotency_rejects_in_progress(
        self, orchestrator, sample_order, stocked_items, stock_repo, idempotency
    ):
        """Test that concurrent calls with same key are rejected."""
        # Manually set key to "processing" state
        await idempotency.check_and_store("in-progress-key")

        with pytest.raises(SagaExecutionError, match="already in progress"):
            await orchestrator.execute(
                sample_order, idempotency_key="in-progress-key"
            )
