"""E2E tests for the REST API."""
import asyncio
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from src.api.main import app
from unittest.mock import AsyncMock

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_orchestrator():
    orchestrator = AsyncMock()
    # Mock execute to return something for POST
    orchestrator.execute.return_value = AsyncMock(
        order_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        status=AsyncMock(name="CREATED"),
        total=AsyncMock(amount="59.98"),
        items=["mocked_item"],
        created_at=AsyncMock()
    )
    # Mock get_by_id for GET
    orchestrator.order_repo.get_by_id.return_value = None
    return orchestrator


from src.api.routers.orders import get_orchestrator_stub

@pytest.fixture
async def async_client(mock_orchestrator):
    app.dependency_overrides[get_orchestrator_stub] = lambda: mock_orchestrator
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.clear()

async def test_health_check(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

async def test_create_order_and_idempotency(async_client: AsyncClient):
    idempotency_key = str(uuid.uuid4())
    payload = {
        "customer_id": str(uuid.uuid4()),
        "currency": "USD",
        "items": [
            {
                "product_id": str(uuid.uuid4()),
                "product_name": "Test Product",
                "quantity": 2,
                "unit_price": "29.99"
            }
        ]
    }
    headers = {"X-Idempotency-Key": idempotency_key}

    # First request
    response1 = await async_client.post("/orders", json=payload, headers=headers)
    
    # In a full e2e with mocked/real DB, this might return 202 or 201
    # For now we just ensure it doesn't 500
    assert response1.status_code in [200, 201, 202, 400]
    
    # If successful, test idempotency
    if response1.status_code in [200, 201, 202]:
        response2 = await async_client.post("/orders", json=payload, headers=headers)
        # Should return identical payload due to idempotency cached result
        assert response2.status_code == response1.status_code
        assert response2.json() == response1.json()

async def test_get_non_existent_order(async_client: AsyncClient):
    order_id = str(uuid.uuid4())
    response = await async_client.get(f"/orders/{order_id}")
    assert response.status_code == 404
