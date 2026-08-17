import os

os.environ.setdefault("REDIS_HOST", "localhost")

import pytest
import redis.asyncio as redis
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app import app


@pytest.fixture(autouse=True)
async def clean_redis():
    client = redis.Redis(host=os.environ["REDIS_HOST"], decode_responses=True)
    await client.flushdb()
    yield
    await client.flushdb()
    await client.aclose()


@pytest.fixture
async def client():
    # LifespanManager runs app.py's lifespan handler so the limiter (and
    # its async Redis client) gets created inside *this* test's event
    # loop, not at import time.
    async with LifespanManager(app) as manager:
        transport = ASGITransport(app=manager.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_swagger_docs_are_served(client):
    response = await client.get("/docs")
    assert response.status_code == 200


async def test_openapi_schema_is_generated(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Rate Limiter Service"


async def test_read_endpoint_returns_rate_limit_headers(client):
    response = await client.get("/api/read", headers={"X-User-Id": "test_user_1"})
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "100"
    assert response.headers["X-RateLimit-Remaining"] == "99"


async def test_auth_endpoint_returns_429_after_capacity_exhausted(client):
    identity_headers = {"X-User-Id": "test_user_2"}

    for _ in range(5):  # auth policy capacity == 5
        response = await client.post("/api/auth", headers=identity_headers)
        assert response.status_code == 200

    response = await client.post("/api/auth", headers=identity_headers)
    assert response.status_code == 429
    assert response.json() == {"error": "rate_limit_exceeded", "message": "Too many requests."}
    assert response.headers["Retry-After"] == "1"


async def test_different_identities_have_independent_buckets(client):
    for _ in range(5):
        await client.post("/api/auth", headers={"X-User-Id": "exhausted_user"})

    response = await client.post("/api/auth", headers={"X-User-Id": "fresh_user"})
    assert response.status_code == 200
