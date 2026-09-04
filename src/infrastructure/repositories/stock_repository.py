"""Stock Repository — Interface and in-memory implementation."""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain import StockItem


class StockRepository(ABC):
    """Abstract repository for StockItem aggregate persistence."""

    @abstractmethod
    async def get_by_product(self, product_id: UUID) -> StockItem | None: ...

    @abstractmethod
    async def save(self, item: StockItem) -> None: ...

    @abstractmethod
    async def update_with_version(
        self, item: StockItem, expected_version: int
    ) -> bool:
        """Optimistic lock update. Returns False if version mismatch."""
        ...


class InMemoryStockRepository(StockRepository):
    """In-memory implementation with optimistic concurrency control."""

    def __init__(self):
        self._stock: dict[UUID, StockItem] = {}

    async def seed(self, item: StockItem) -> None:
        """Seed stock data (test helper)."""
        self._stock[item.product_id] = item

    async def get_by_product(self, product_id: UUID) -> StockItem | None:
        return self._stock.get(product_id)

    async def save(self, item: StockItem) -> None:
        self._stock[item.product_id] = item

    async def update_with_version(
        self, item: StockItem, expected_version: int
    ) -> bool:
        current = self._stock.get(item.product_id)
        if current is None or current.version != expected_version:
            return False
        item.version = current.version + 1
        self._stock[item.product_id] = item
        return True
