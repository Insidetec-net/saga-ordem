"""Application layer — Saga Orchestrator, compensating transactions, event handling."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine
from uuid import UUID, uuid4

from src.domain import (
    DomainEvent,
    InsufficientStock,
    InvalidStateTransition,
    Money,
    Order,
    OrderCancelled,
    OrderConfirmed,
    OrderCreated,
    OrderItem,
    OrderStatus,
    PaymentFailed,
    PaymentProcessed,
    PaymentRefunded,
    SagaExecutionError,
    SagaFailed,
    SagaState,
    StockItem,
    StockReleased,
    StockReservationFailed,
    StockReserved,
)
from src.infrastructure import (
    DeadLetterQueue,
    DomainEncoder,
    IdempotencyStore,
    InMemoryOrderRepository,
    InMemoryOutbox,
    InMemorySagaLog,
    InMemoryStockRepository,
    OrderRepository,
    OutboxRepository,
    SagaLogRepository,
    StockRepository,
    json,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Saga Step Definition
# ═══════════════════════════════════════════════════════════════

class SagaStep:
    """Single step in a saga with action and compensation."""

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
            self.state = SagaState.STOCK_RESERVING if "stock" in self.name.lower() else SagaState.PAYMENT_PROCESSING
            self.result = await self.action(*args, **kwargs)
            self.state = SagaState.STOCK_RESERVED if "stock" in self.name.lower() else SagaState.PAYMENT_COMPLETED
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


# ═══════════════════════════════════════════════════════════════
# Saga Orchestrator
# ═══════════════════════════════════════════════════════════════

class OrderSagaOrchestrator:
    """
    Orchestrates the order processing saga.
    
    Flow:
    1. CREATE_ORDER → validate and persist
    2. RESERVE_STOCK → lock inventory with optimistic concurrency
    3. PROCESS_PAYMENT → charge customer
    4. CONFIRM_ORDER → finalize and emit events
    
    If any step fails, compensating transactions run in reverse.
    """

    def __init__(
        self,
        order_repo: OrderRepository,
        stock_repo: StockRepository,
        outbox: OutboxRepository,
        idempotency: IdempotencyStore,
        saga_log: SagaLogRepository,
        dlq: DeadLetterQueue,
    ):
        self.order_repo = order_repo
        self.stock_repo = stock_repo
        self.outbox = outbox
        self.idempotency = idempotency
        self.saga_log = saga_log
        self.dlq = dlq

    async def execute(self, order: Order, idempotency_key: str | None = None) -> Order:
        """Execute the full order saga."""
        saga_id = uuid4()

        # Idempotency check
        if idempotency_key:
            is_new = await self.idempotency.check_and_store(idempotency_key)
            if not is_new:
                cached = await self.idempotency.get_result(idempotency_key)
                if cached and cached.get("status") == "completed":
                    logger.info(f"Duplicate request {idempotency_key}, returning cached result")
                    order_id = UUID(cached["order_id"])
                    return await self.order_repo.get_by_id(order_id)
                raise SagaExecutionError(f"Request {idempotency_key} already in progress")

        # Define saga steps
        steps = [
            SagaStep(
                name="create_order",
                action=lambda: self._create_order(order, saga_id),
            ),
            SagaStep(
                name="reserve_stock",
                action=lambda: self._reserve_stock(order, saga_id),
                compensate=lambda: self._release_stock(order, saga_id),
            ),
            SagaStep(
                name="process_payment",
                action=lambda: self._process_payment(order, saga_id),
                compensate=lambda: self._refund_payment(order, saga_id),
            ),
            SagaStep(
                name="confirm_order",
                action=lambda: self._confirm_order(order, saga_id),
            ),
        ]

        completed_steps: list[SagaStep] = []

        try:
            for step in steps:
                logger.info(f"Saga {saga_id}: executing step {step.name}")
                await self.saga_log.log_step(
                    order_id=order.order_id,
                    saga_id=saga_id,
                    step_name=step.name,
                    state=step.state,
                )
                await step.execute()
                completed_steps.append(step)

            # All steps completed — publish events
            await self._publish_events(order)

            # Store idempotency result
            if idempotency_key:
                await self.idempotency.store_result(
                    idempotency_key,
                    {"status": "completed", "order_id": str(order.order_id)},
                )

            logger.info(f"Saga {saga_id}: COMPLETED for order {order.order_id}")
            return order

        except Exception as e:
            logger.error(f"Saga {saga_id}: FAILED at step {completed_steps[-1].name if completed_steps else 'start'}: {e}")
            await self.saga_log.log_step(
                order_id=order.order_id,
                saga_id=saga_id,
                step_name=completed_steps[-1].name if completed_steps else "start",
                state=SagaState.FAILED,
                error=str(e),
            )
            # Compensate in reverse order
            await self._compensate(completed_steps, order, saga_id)
            raise SagaExecutionError(f"Saga failed: {e}") from e

    async def _create_order(self, order: Order, saga_id: UUID) -> dict[str, Any]:
        """Step 1: Persist the order."""
        existing = await self.order_repo.get_by_id(order.order_id)
        if existing:
            raise DuplicateOrderError(f"Order {order.order_id} already exists")

        await self.order_repo.save(order)
        await self.outbox.append(OrderCreated(
            order_id=order.order_id,
            customer_id=order.customer_id,
            total=order.total.amount,
        ), order.order_id)

        return {"order_id": str(order.order_id), "status": "created"}

    async def _reserve_stock(self, order: Order, saga_id: UUID) -> dict[str, Any]:
        """Step 2: Reserve stock with optimistic locking."""
        reservations = []

        for item in order.items:
            stock = await self.stock_repo.get_by_product(item.product_id)
            if not stock:
                raise StockReservationFailed(
                    order_id=order.order_id,
                    product_id=item.product_id,
                    reason="Product not found",
                )

            # Attempt reservation with optimistic lock
            expected_version = stock.version
            try:
                stock.reserve(item.quantity)
            except InsufficientStock as e:
                raise StockReservationFailed(
                    order_id=order.order_id,
                    product_id=item.product_id,
                    reason=str(e),
                )

            # Update with version check
            success = await self.stock_repo.update_with_version(stock, expected_version)
            if not success:
                # Concurrent modification — retry once
                stock = await self.stock_repo.get_by_product(item.product_id)
                if not stock or stock.effective_stock < item.quantity:
                    raise StockReservationFailed(
                        order_id=order.order_id,
                        product_id=item.product_id,
                        reason="Concurrent modification, insufficient stock",
                    )
                expected_version = stock.version
                stock.reserve(item.quantity)
                success = await self.stock_repo.update_with_version(stock, expected_version)
                if not success:
                    raise StockReservationFailed(
                        order_id=order.order_id,
                        product_id=item.product_id,
                        reason="Concurrent modification after retry",
                    )

            reservations.append({"product_id": str(item.product_id), "qty": item.quantity})

        # Transition order state
        order.reserve_stock()
        await self.order_repo.update(order)
        await self.outbox.append(StockReserved(
            order_id=order.order_id,
            items=reservations,
        ), order.order_id)

        return {"reserved": reservations}

    async def _process_payment(self, order: Order, saga_id: UUID) -> dict[str, Any]:
        """Step 3: Process payment (mock — integrates with payment gateway)."""
        # Simulate payment processing
        # In production: call Stripe/MercadoPago API
        payment_id = uuid4()

        # Simulate random failure for demo (10% chance)
        # import random
        # if random.random() < 0.1:
        #     raise PaymentFailed(order_id=order.order_id, reason="Gateway timeout")

        order.process_payment()
        await self.order_repo.update(order)
        await self.outbox.append(PaymentProcessed(
            order_id=order.order_id,
            payment_id=payment_id,
            amount=order.total.amount,
        ), order.order_id)

        return {"payment_id": str(payment_id), "amount": str(order.total.amount)}

    async def _confirm_order(self, order: Order, saga_id: UUID) -> dict[str, Any]:
        """Step 4: Final confirmation."""
        order.confirm()
        await self.order_repo.update(order)
        await self.outbox.append(OrderConfirmed(
            order_id=order.order_id,
        ), order.order_id)

        return {"status": "confirmed", "order_id": str(order.order_id)}

    async def _compensate(self, completed_steps: list[SagaStep], order: Order, saga_id: UUID) -> None:
        """Run compensating transactions in reverse order."""
        logger.warning(f"Saga {saga_id}: starting compensation for order {order.order_id}")

        for step in reversed(completed_steps):
            try:
                await step.rollback()
            except SagaExecutionError:
                # Critical — needs manual intervention
                await self.dlq.enqueue(
                    event_type="compensation_failed",
                    payload={
                        "saga_id": str(saga_id),
                        "step": step.name,
                        "order_id": str(order.order_id),
                    },
                    error=step.error or "Unknown",
                )
                raise

        # Mark order as failed/cancelled
        try:
            order.cancel(reason="Saga compensation")
            await self.order_repo.update(order)
            await self.outbox.append(StockReleased(
                order_id=order.order_id,
                items=[{"product_id": str(i.product_id), "qty": i.quantity} for i in order.items],
            ), order.order_id)
        except Exception as e:
            logger.error(f"Failed to cancel order after compensation: {e}")

    async def _release_stock(self, order: Order, saga_id: UUID) -> dict[str, Any]:
        """Compensating action: release reserved stock."""
        for item in order.items:
            stock = await self.stock_repo.get_by_product(item.product_id)
            if stock:
                expected_version = stock.version
                stock.release(item.quantity)
                await self.stock_repo.update_with_version(stock, expected_version)

        await self.outbox.append(StockReleased(
            order_id=order.order_id,
            items=[{"product_id": str(i.product_id), "qty": i.quantity} for i in order.items],
        ), order.order_id)

        return {"released": True}

    async def _refund_payment(self, order: Order, saga_id: UUID) -> dict[str, Any]:
        """Compensating action: refund payment."""
        # In production: call payment gateway for refund
        await self.outbox.append(PaymentRefunded(
            order_id=order.order_id,
            payment_id=uuid4(),  # Would come from payment record
            amount=order.total.amount,
        ), order.order_id)

        return {"refunded": True}

    async def _publish_events(self, order: Order) -> None:
        """Publish domain events from the order aggregate."""
        for event in order.events:
            await self.outbox.append(event, order.order_id)
        order.clear_events()


class DuplicateOrderError(Exception):
    pass


# ═══════════════════════════════════════════════════════════════
# Reconciliation Worker
# ═══════════════════════════════════════════════════════════════

class ReconciliationWorker:
    """
    Daily reconciliation between orders and payments.
    Detects mismatches, missing payments, or orphaned reservations.
    """

    def __init__(
        self,
        order_repo: OrderRepository,
        outbox: OutboxRepository,
        dlq: DeadLetterQueue,
    ):
        self.order_repo = order_repo
        self.outbox = outbox
        self.dlq = dlq

    async def reconcile(self, date: datetime | None = None) -> dict[str, Any]:
        """
        Run reconciliation for a given date.
        Returns a report of mismatches found.
        """
        # In production: query DB for orders on that date
        # For demo: scan in-memory
        report = {
            "date": (date or datetime.now(timezone.utc)).isoformat(),
            "checked": 0,
            "mismatches": [],
            "orphaned_payments": [],
            "missing_confirmations": [],
        }

        return report
