"""PostgreSQL Stock Repository — Production implementation with optimistic locking."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain import StockItem
from src.infrastructure.database.models import StockItemModel
from src.infrastructure.repositories.stock_repository import StockRepository


class PgStockRepository(StockRepository):
    """PostgreSQL-backed stock repository with optimistic concurrency control.

    Uses WHERE version = expected_version in UPDATE statements to prevent
    lost updates from concurrent modifications.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_product(self, product_id: UUID) -> StockItem | None:
        stmt = select(StockItemModel).where(
            StockItemModel.product_id == product_id
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def save(self, item: StockItem) -> None:
        model = StockItemModel(
            product_id=item.product_id,
            product_name=item.product_name,
            available_qty=item.available_qty,
            reserved_qty=item.reserved_qty,
            version=item.version,
        )
        self._session.add(model)
        await self._session.flush()

    async def update_with_version(
        self, item: StockItem, expected_version: int
    ) -> bool:
        """Optimistic lock via SQL WHERE clause.

        UPDATE stock_items
        SET ..., version = version + 1
        WHERE product_id = :id AND version = :expected_version

        Returns True if exactly one row was updated (version matched).
        Returns False if zero rows updated (concurrent modification detected).
        """
        stmt = (
            update(StockItemModel)
            .where(
                StockItemModel.product_id == item.product_id,
                StockItemModel.version == expected_version,
            )
            .values(
                available_qty=item.available_qty,
                reserved_qty=item.reserved_qty,
                version=expected_version + 1,
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()

        # rowcount == 1 means version matched and row was updated
        return result.rowcount == 1

    @staticmethod
    def _to_domain(model: StockItemModel) -> StockItem:
        return StockItem(
            product_id=model.product_id,
            product_name=model.product_name,
            available_qty=model.available_qty,
            reserved_qty=model.reserved_qty,
            version=model.version,
        )
