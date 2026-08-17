import time
from dataclasses import dataclass
from enum import Enum

import redis

from metrics import (
    rate_limit_check_duration_seconds,
    rate_limit_checks_total,
    rate_limit_redis_failures_total,
)
from redis_client import RedisScriptRunner


class FailMode(Enum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class RateLimitPolicy:
    endpoint_class: str
    capacity: int
    refill_rate: float
    fail_mode: FailMode


@dataclass
class RateLimitDecision:
    allowed: bool
    remaining: float
    limit: int


class TokenBucketLimiter:
    """Given an identity + policy, decides allow/deny via Redis.
    Knows nothing about HTTP — that lives in middleware.py.
    """

    def __init__(self, script_runner: RedisScriptRunner):
        self._script_runner = script_runner

    async def check(self, identity: str, policy: RateLimitPolicy) -> RateLimitDecision:
        key = f"ratelimit:{identity}:{policy.endpoint_class}"
        start = time.monotonic()
        try:
            allowed, remaining = await self._script_runner.check_and_consume(
                key, policy.capacity, policy.refill_rate
            )
            rate_limit_check_duration_seconds.labels(policy.endpoint_class).observe(
                time.monotonic() - start
            )
            outcome = "allowed" if allowed else "denied"
            rate_limit_checks_total.labels(policy.endpoint_class, outcome).inc()
            return RateLimitDecision(allowed, remaining, policy.capacity)
        except redis.RedisError:
            rate_limit_redis_failures_total.labels(
                policy.endpoint_class, policy.fail_mode.value
            ).inc()
            fallback_allowed = policy.fail_mode == FailMode.OPEN
            return RateLimitDecision(
                allowed=fallback_allowed,
                remaining=policy.capacity if fallback_allowed else 0,
                limit=policy.capacity,
            )
