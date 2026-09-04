"""API Layer — FastAPI endpoints."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# DTOs (Data Transfer Objects)
# ═══════════════════════════════════════════════════════════════


class CreateOrderItemDTO(BaseModel):
    product_id: UUID
    product_name: str
    quantity: int = Field(ge=1)
    unit_price: Decimal = Field(ge=0)


class CreateOrderDTO(BaseModel):
    customer_id: UUID
    items: list[CreateOrderItemDTO]
    payment_method: str = "PIX"
    idempotency_key: str | None = None
    shipping_address: dict[str, str] | None = None


class OrderResponseDTO(BaseModel):
    order_id: UUID
    customer_id: UUID
    status: str
    total: Decimal
    items_count: int
    created_at: str


class SagaStatusDTO(BaseModel):
    saga_id: UUID
    order_id: UUID
    current_state: str
    steps: list[dict[str, Any]]


class ReconciliationReportDTO(BaseModel):
    date: str
    checked: int
    mismatches: list[dict[str, Any]]


# ═══════════════════════════════════════════════════════════════
# FastAPI Application Factory
# ═══════════════════════════════════════════════════════════════


def create_app(
    orchestrator,  # OrderSagaOrchestrator
    reconciliation,  # ReconciliationWorker
    order_repo,  # OrderRepository
    saga_log,  # SagaLogRepository
):
    from fastapi import BackgroundTasks, FastAPI, HTTPException

    app = FastAPI(
        title="Order Processing System",
        description="Saga Pattern with idempotency, outbox, and reconciliation",
        version="1.0.0",
    )

    @app.post("/orders", response_model=OrderResponseDTO, status_code=201)
    async def create_order(dto: CreateOrderDTO):
        """Create a new order — saga starts."""
        from src.domain import Address, Money, Order, OrderItem, PaymentMethod

        order_id = uuid4()

        payment_method = (
            PaymentMethod[dto.payment_method]
            if dto.payment_method in PaymentMethod.__members__
            else PaymentMethod.PIX
        )

        items = [
            OrderItem(
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=item.quantity,
                unit_price=Money(item.unit_price),
            )
            for item in dto.items
        ]

        address = None
        if dto.shipping_address:
            address = Address(
                street=dto.shipping_address.get("street", ""),
                city=dto.shipping_address.get("city", ""),
                state=dto.shipping_address.get("state", ""),
                zip_code=dto.shipping_address.get("zip_code", ""),
            )

        order = Order(
            order_id=order_id,
            customer_id=dto.customer_id,
            items=items,
            shipping_address=address,
            payment_method=payment_method,
        )

        try:
            completed_order = await orchestrator.execute(
                order,
                idempotency_key=dto.idempotency_key or str(order_id),
            )
        except Exception as e:
            logger.error(f"Order creation failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

        return OrderResponseDTO(
            order_id=completed_order.order_id,
            customer_id=completed_order.customer_id,
            status=completed_order.status.name,
            total=completed_order.total.amount,
            items_count=len(completed_order.items),
            created_at=completed_order.created_at.isoformat(),
        )

    @app.get("/orders/{order_id}", response_model=OrderResponseDTO)
    async def get_order(order_id: UUID):
        """Get order by ID."""
        order = await order_repo.get_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        return OrderResponseDTO(
            order_id=order.order_id,
            customer_id=order.customer_id,
            status=order.status.name,
            total=order.total.amount,
            items_count=len(order.items),
            created_at=order.created_at.isoformat(),
        )

    @app.get("/saga/{saga_id}/status", response_model=SagaStatusDTO)
    async def get_saga_status(saga_id: UUID):
        """Get saga execution status."""
        history = await saga_log.get_saga_history(saga_id)
        if not history:
            raise HTTPException(status_code=404, detail="Saga not found")

        steps = [
            {
                "step": h["step_name"],
                "state": h["state"],
                "error": h.get("error"),
                "timestamp": h["created_at"].isoformat(),
            }
            for h in history
        ]

        current_state = history[-1]["state"] if history else "UNKNOWN"

        return SagaStatusDTO(
            saga_id=saga_id,
            order_id=history[0]["order_id"] if history else UUID(int=0),
            current_state=current_state,
            steps=steps,
        )

    @app.post(
        "/reconciliation/run", response_model=ReconciliationReportDTO
    )
    async def run_reconciliation(background_tasks: BackgroundTasks):
        """Trigger daily reconciliation."""
        report = await reconciliation.reconcile()
        return ReconciliationReportDTO(**report)

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return app
