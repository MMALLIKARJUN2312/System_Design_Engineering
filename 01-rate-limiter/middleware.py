from fastapi import Request, Response

from limiter import RateLimitPolicy, TokenBucketLimiter


class RateLimitExceeded(Exception):
    """Raised by the dependency below and turned into a 429 JSON response
    by the exception handler registered in app.py. A dedicated exception
    (rather than FastAPI's built-in HTTPException) keeps full control over
    the response body shape and headers, matching the documented API
    contract instead of FastAPI's default {"detail": ...} wrapping.
    """

    def __init__(self, headers: dict[str, str]):
        self.headers = headers


def rate_limit_dependency(policy: RateLimitPolicy, identity_fn):
    """FastAPI dependency factory: resolves identity, checks the limiter,
    and either raises RateLimitExceeded (→ 429) or attaches X-RateLimit-*
    headers to the in-flight response before the route handler runs.

    The limiter itself is read from request.app.state (set up in app.py's
    lifespan handler) rather than captured as a closure, since this
    factory runs at import time — before the limiter's async Redis client
    exists.
    """

    async def dependency(request: Request, response: Response) -> None:
        limiter: TokenBucketLimiter = request.app.state.limiter
        identity = identity_fn(request)
        decision = await limiter.check(identity, policy)

        headers = {
            "X-RateLimit-Limit": str(decision.limit),
            "X-RateLimit-Remaining": str(int(decision.remaining)),
        }

        if not decision.allowed:
            raise RateLimitExceeded(headers={**headers, "Retry-After": "1"})

        for name, value in headers.items():
            response.headers[name] = value

    return dependency
