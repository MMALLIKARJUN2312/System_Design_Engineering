import asyncio
import os

import pytest
import pytest_asyncio
import redis.asyncio as redis

from redis_client import RedisScriptRunner

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "scripts", "token_bucket.lua")


@pytest_asyncio.fixture
async def redis_client():
    client = redis.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=os.environ.get("REDIS_PASSWORD"),
        db=15,
        decode_responses=True,
    )
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
def script_runner(redis_client):
    return RedisScriptRunner(redis_client, SCRIPT_PATH)


async def test_first_request_starts_with_full_bucket(script_runner):
    allowed, remaining = await script_runner.check_and_consume("k1", capacity=10, refill_rate=1)
    assert allowed is True
    assert remaining == 9.0  # started full (10), consumed 1


async def test_bucket_exhausts_after_capacity_requests(script_runner):
    for _ in range(10):
        allowed, _ = await script_runner.check_and_consume("k2", capacity=10, refill_rate=1)
        assert allowed is True

    allowed, remaining = await script_runner.check_and_consume("k2", capacity=10, refill_rate=1)
    assert allowed is False
    # Not an exact 0.0: the wall-clock time spent making 10 sequential
    # calls refills a small fraction of a token at refill_rate=1/sec, so
    # a strict equality check here would be flaky by construction rather
    # than catching a real bug.
    assert remaining < 0.05


async def test_tokens_refill_over_time(script_runner):
    for _ in range(10):
        await script_runner.check_and_consume("k3", capacity=10, refill_rate=5)  # 5 tokens/sec

    await asyncio.sleep(1.1)  # should refill ~5-5.5 tokens

    allowed, remaining = await script_runner.check_and_consume("k3", capacity=10, refill_rate=5)
    assert allowed is True
    assert remaining >= 3.5  # allow timing slack in CI


async def test_bucket_never_exceeds_capacity_even_after_long_idle(script_runner):
    await script_runner.check_and_consume("k4", capacity=10, refill_rate=100)
    await asyncio.sleep(1)  # would refill "1000" tokens at this rate if uncapped

    allowed, remaining = await script_runner.check_and_consume("k4", capacity=10, refill_rate=100)
    assert allowed is True
    assert remaining == 9.0  # capped at capacity (10), not 1000+


async def test_key_expires_after_idle_ttl(script_runner, redis_client):
    await script_runner.check_and_consume("k5", capacity=10, refill_rate=1)
    ttl = await redis_client.ttl("k5")
    assert ttl > 0
