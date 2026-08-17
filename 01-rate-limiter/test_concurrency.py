import asyncio
import os

import redis.asyncio as redis

from redis_client import RedisScriptRunner

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "scripts", "token_bucket.lua")


async def test_concurrent_requests_never_exceed_capacity():
    """Proves the check-and-consume Lua script closes the race condition
    described in the design doc: with a naive HGET-then-HSET
    implementation, this test flakes with allowed_count > capacity because
    multiple concurrent callers read the same stale value before any of
    them writes back. With the atomic script, it's deterministic every
    run, regardless of how many concurrent asyncio tasks (mirroring
    concurrent in-flight FastAPI requests) hit it at once.
    """
    client = redis.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=os.environ.get("REDIS_PASSWORD"),
        db=15,
        decode_responses=True,
    )
    await client.flushdb()
    runner = RedisScriptRunner(client, SCRIPT_PATH)

    capacity = 10

    async def fire_request():
        allowed, _remaining = await runner.check_and_consume(
            "race_key", capacity=capacity, refill_rate=0.001
        )
        return allowed

    results = await asyncio.gather(*(fire_request() for _ in range(50)))
    await client.aclose()

    allowed_count = sum(results)
    assert allowed_count == capacity
