"""Saga Step — Single step definition with action and compensation."""
from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

from src.domain import SagaExecutionError, SagaState

logger = logging.getLogger(__name__)


class SagaStep:
    """Single step in a saga with action and compensation.

    Each step tracks its own state, error, and result.
    If execution fails, the orchestrator calls rollback()
    which invokes the compensating transaction.
    """

    def __init__(
        self,
        name: str,
        action: Callable[..., Coroutine],
        compensate: Callable[..., Coroutine] | None = None,
    ):
        self.name = name
        self.action = action
        self.compensate = compensate
        self.state = SagaState.STARTED
        self.error: str | None = None
        self.result: Any = None

    async def execute(self, *args, **kwargs) -> Any:
        try:
            self.state = (
                SagaState.STOCK_RESERVING
                if "stock" in self.name.lower()
                else SagaState.PAYMENT_PROCESSING
            )
            self.result = await self.action(*args, **kwargs)
            self.state = (
                SagaState.STOCK_RESERVED
                if "stock" in self.name.lower()
                else SagaState.PAYMENT_COMPLETED
            )
            return self.result
        except Exception as e:
            self.error = str(e)
            self.state = SagaState.FAILED
            raise

    async def rollback(self, *args, **kwargs) -> Any:
        if self.compensate:
            try:
                return await self.compensate(*args, **kwargs)
            except Exception as e:
                logger.error(f"Compensation failed for {self.name}: {e}")
                raise SagaExecutionError(
                    f"CRITICAL: Compensation failed for step {self.name}: {e}"
                )
        return None
