import time

import redis.asyncio as redis


class RedisScriptRunner:
    """Thin async transport layer: owns the Redis connection and the
    compiled Lua script. Knows nothing about rate-limiting semantics —
    that lives in limiter.py.

    Uses redis.asyncio (not the sync redis-py client) because this is
    called from FastAPI's async request path — a blocking sync client
    here would stall the event loop for every other in-flight request
    while waiting on the network round trip.
    """

    def __init__(self, redis_client: redis.Redis, script_path: str):
        self._redis = redis_client
        with open(script_path) as f:
            self._script = self._redis.register_script(f.read())

    async def check_and_consume(self, key: str, capacity: int, refill_rate: float, cost: int = 1):
        allowed, remaining = await self._script(
            keys=[key],
            args=[capacity, refill_rate, time.time(), cost],
        )
        return bool(int(allowed)), float(remaining)


def build_redis_client(host: str, port: int = 6379, password: str | None = None) -> redis.Redis:
    return redis.Redis(
        host=host,
        port=port,
        password=password,
        decode_responses=True,
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
    )
