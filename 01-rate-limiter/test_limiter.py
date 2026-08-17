from unittest.mock import AsyncMock

import redis

from limiter import FailMode, RateLimitPolicy, TokenBucketLimiter


async def test_fail_open_allows_request_when_redis_down():
    script_runner = AsyncMock()
    script_runner.check_and_consume.side_effect = redis.RedisError("connection refused")
    limiter = TokenBucketLimiter(script_runner)
    policy = RateLimitPolicy("read", capacity=100, refill_rate=10, fail_mode=FailMode.OPEN)

    decision = await limiter.check("user_1", policy)

    assert decision.allowed is True
    assert decision.remaining == 100


async def test_fail_closed_denies_request_when_redis_down():
    script_runner = AsyncMock()
    script_runner.check_and_consume.side_effect = redis.RedisError("connection refused")
    limiter = TokenBucketLimiter(script_runner)
    policy = RateLimitPolicy("auth", capacity=5, refill_rate=0.1, fail_mode=FailMode.CLOSED)

    decision = await limiter.check("user_1", policy)

    assert decision.allowed is False
    assert decision.remaining == 0


async def test_allowed_request_passes_through_script_result():
    script_runner = AsyncMock()
    script_runner.check_and_consume.return_value = (True, 42.0)
    limiter = TokenBucketLimiter(script_runner)
    policy = RateLimitPolicy("read", capacity=100, refill_rate=10, fail_mode=FailMode.OPEN)

    decision = await limiter.check("user_1", policy)

    assert decision.allowed is True
    assert decision.remaining == 42.0


async def test_denied_request_passes_through_script_result():
    script_runner = AsyncMock()
    script_runner.check_and_consume.return_value = (False, 0.0)
    limiter = TokenBucketLimiter(script_runner)
    policy = RateLimitPolicy("write", capacity=20, refill_rate=2, fail_mode=FailMode.OPEN)

    decision = await limiter.check("user_1", policy)

    assert decision.allowed is False
    assert decision.remaining == 0.0


async def test_redis_key_is_namespaced_by_identity_and_endpoint_class():
    script_runner = AsyncMock()
    script_runner.check_and_consume.return_value = (True, 10.0)
    limiter = TokenBucketLimiter(script_runner)
    policy = RateLimitPolicy("write", capacity=20, refill_rate=2, fail_mode=FailMode.OPEN)

    await limiter.check("user_42", policy)

    called_key = script_runner.check_and_consume.call_args[0][0]
    assert called_key == "ratelimit:user_42:write"
