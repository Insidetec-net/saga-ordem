"""Order Repository — Interface and in-memory implementation."""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain import Order


class OrderRepository(ABC):
    """Abstract repository for Order aggregate persistence."""

    @abstractmethod
    async def save(self, order: Order) -> None: ...

    @abstractmethod
    async def get_by_id(self, order_id: UUID) -> Order | None: ...

    @abstractmethod
    async def update(self, order: Order) -> None: ...

    @abstractmethod
    async def list_by_customer(
        self, customer_id: UUID, limit: int = 50
    ) -> list[Order]: ...


class InMemoryOrderRepository(OrderRepository):
    """In-memory implementation for tests and local development."""

    def __init__(self):
        self._orders: dict[UUID, Order] = {}

    async def save(self, order: Order) -> None:
        self._orders[order.order_id] = order

    async def get_by_id(self, order_id: UUID) -> Order | None:
        return self._orders.get(order_id)

    async def update(self, order: Order) -> None:
        if order.order_id not in self._orders:
            raise ValueError(f"Order {order.order_id} not found")
        self._orders[order.order_id] = order

    async def list_by_customer(
        self, customer_id: UUID, limit: int = 50
    ) -> list[Order]:
        return [
            o
            for o in self._orders.values()
            if o.customer_id == customer_id
        ][:limit]
