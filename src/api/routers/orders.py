"""Orders router — endpoints for creating and querying orders."""

import uuid
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException

from src.api.schemas import OrderCreateRequest, OrderResponse
from src.application import OrderSagaOrchestrator
from src.domain.exceptions import DomainError, ConcurrencyException
from src.domain import OrderItem, Order, Money

# In a real app we'd import the factory from main, but to avoid circular imports:
# We'll pass the orchestrator dependency from main.py via Depends.
def get_orchestrator_stub() -> OrderSagaOrchestrator:
    raise NotImplementedError()

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("", response_model=dict, status_code=202)
async def create_order(
    payload: OrderCreateRequest,
    x_idempotency_key: str = Header(..., description="Unique key for idempotency"),
    orchestrator: OrderSagaOrchestrator = Depends(get_orchestrator_stub),
):
    """Create a new order and start the Saga."""
    order_id = uuid.uuid4()
    domain_items = []
    for item in payload.items:
        domain_items.append(
            OrderItem(
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=item.quantity,
                unit_price=Money(Decimal(item.unit_price), payload.currency),
            )
        )

    order = Order(
        order_id=order_id,
        customer_id=payload.customer_id,
        items=domain_items,
    )

    try:
        completed = await orchestrator.execute(
            order, idempotency_key=x_idempotency_key
        )
        return {"order_id": completed.order_id, "status": completed.status.name}

    except ConcurrencyException as e:
        raise HTTPException(status_code=409, detail=str(e))
    except DomainError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Order creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    orchestrator: OrderSagaOrchestrator = Depends(get_orchestrator_stub),
):
    """Retrieve order details."""
    order = await orchestrator.order_repo.get_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Map domain entity back to response schema
    return OrderResponse(
        id=order.id,
        customer_id=order.customer_id,
        status=order.status.value,
        total_amount=str(order.total_amount.amount),
        currency=order.total_amount.currency,
        items=[
            {
                "product_id": item.product_id,
                "product_name": getattr(item, "product_name", "Unknown"), # Fallback if DB doesn't have it loaded
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
            }
            for item in order.items
        ],
    )
