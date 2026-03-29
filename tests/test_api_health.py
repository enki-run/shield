import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.core.database import close_db


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok(setup_test_dirs):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    await close_db()


@pytest.mark.asyncio
async def test_health_endpoint_content_type(setup_test_dirs):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert "application/json" in response.headers["content-type"]
    await close_db()


@pytest.mark.asyncio
async def test_unknown_route_returns_404(setup_test_dirs):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/nonexistent")
    assert response.status_code == 404
    await close_db()
