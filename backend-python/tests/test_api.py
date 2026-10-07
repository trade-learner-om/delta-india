from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from cryptobridge.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "UP"
    assert body["service"] == "CryptoBridge"
    assert "marketFeedStatus" in body
    assert "mongoStatus" in body


@pytest.mark.asyncio
async def test_root_health_endpoint():
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] in {"UP", "DEGRADED"}
