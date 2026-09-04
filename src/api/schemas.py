"""Pydantic schemas for the REST API."""

import uuid
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, Field, conlist, ConfigDict


class OrderItemSchema(BaseModel):
    """Schema for items within an order request."""

    product_id: UUID
    product_name: str
    quantity: int = Field(gt=0, description="Quantity must be greater than zero")
    unit_price: str = Field(pattern=r"^\d+\.\d{2}$", description="Price formatted as '10.00'")


class OrderCreateRequest(BaseModel):
    """Payload for creating a new order."""

    customer_id: UUID
    currency: Literal["USD", "BRL", "EUR"] = "USD"
    items: conlist(OrderItemSchema, min_length=1)  # type: ignore


class OrderItemResponse(BaseModel):
    product_id: UUID
    product_name: str
    quantity: int
    unit_price: str


class OrderResponse(BaseModel):
    """Payload returned when querying an order."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    status: str
    total_amount: str
    currency: str
    items: list[OrderItemResponse]
