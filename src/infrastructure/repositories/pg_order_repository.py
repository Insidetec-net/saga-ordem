"""PostgreSQL Order Repository — Production implementation."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain import Address, Money, Order, OrderItem, OrderStatus, PaymentMethod
from src.infrastructure.database.models import OrderItemModel, OrderModel
from src.infrastructure.repositories.order_repository import OrderRepository


class PgOrderRepository(OrderRepository):
    """PostgreSQL-backed order repository using SQLAlchemy async."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, order: Order) -> None:
        model = self._to_model(order)
        self._session.add(model)
        await self._session.flush()

    async def get_by_id(self, order_id: UUID) -> Order | None:
        stmt = select(OrderModel).where(OrderModel.id == order_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def update(self, order: Order) -> None:
        stmt = select(OrderModel).where(OrderModel.id == order.order_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Order {order.order_id} not found")

        model.status = order.status.name
        model.total_amount = float(order.total.amount)
        model.total_currency = order.total.currency
        model.version = order.version
        model.updated_at = order.updated_at
        model.payment_method = order.payment_method.name

        if order.shipping_address:
            model.shipping_street = order.shipping_address.street
            model.shipping_city = order.shipping_address.city
            model.shipping_state = order.shipping_address.state
            model.shipping_zip_code = order.shipping_address.zip_code
            model.shipping_country = order.shipping_address.country

        await self._session.flush()

    async def list_by_customer(
        self, customer_id: UUID, limit: int = 50
    ) -> list[Order]:
        stmt = (
            select(OrderModel)
            .where(OrderModel.customer_id == customer_id)
            .order_by(OrderModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    # ── Mapping helpers ──────────────────────────────────────

    @staticmethod
    def _to_model(order: Order) -> OrderModel:
        """Map domain Order to ORM model."""
        model = OrderModel(
            id=order.order_id,
            customer_id=order.customer_id,
            status=order.status.name,
            payment_method=order.payment_method.name,
            total_amount=float(order.total.amount),
            total_currency=order.total.currency,
            version=order.version,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

        if order.shipping_address:
            model.shipping_street = order.shipping_address.street
            model.shipping_city = order.shipping_address.city
            model.shipping_state = order.shipping_address.state
            model.shipping_zip_code = order.shipping_address.zip_code
            model.shipping_country = order.shipping_address.country

        model.items = [
            OrderItemModel(
                order_id=order.order_id,
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=item.quantity,
                unit_price=float(item.unit_price.amount),
                unit_currency=item.unit_price.currency,
            )
            for item in order.items
        ]

        return model

    @staticmethod
    def _to_domain(model: OrderModel) -> Order:
        """Map ORM model back to domain Order."""
        address = None
        if model.shipping_street:
            address = Address(
                street=model.shipping_street,
                city=model.shipping_city or "",
                state=model.shipping_state or "",
                zip_code=model.shipping_zip_code or "",
                country=model.shipping_country or "BR",
            )

        items = [
            OrderItem(
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=item.quantity,
                unit_price=Money(
                    Decimal(str(item.unit_price)),
                    item.unit_currency,
                ),
            )
            for item in model.items
        ]

        return Order(
            order_id=model.id,
            customer_id=model.customer_id,
            items=items,
            status=OrderStatus[model.status],
            shipping_address=address,
            payment_method=PaymentMethod[model.payment_method],
            total=Money(
                Decimal(str(model.total_amount)),
                model.total_currency,
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )
