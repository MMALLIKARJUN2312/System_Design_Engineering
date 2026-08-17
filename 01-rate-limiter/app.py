import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse

from config import POLICIES
from limiter import TokenBucketLimiter
from metrics import generate_metrics
from middleware import RateLimitExceeded, rate_limit_dependency
from redis_client import RedisScriptRunner, build_redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Built inside lifespan, not at module import time: an async Redis
    # client created before the event loop is actually running binds to
    # the wrong loop, surfacing as "RuntimeError: Event loop is closed"
    # under multiple workers, --reload, or (as caught here) per-test
    # event loops in the test suite.
    redis_client = build_redis_client(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=os.environ.get("REDIS_PASSWORD"),
    )
    script_path = os.path.join(os.path.dirname(__file__), "scripts", "token_bucket.lua")
    script_runner = RedisScriptRunner(redis_client, script_path)
    app.state.limiter = TokenBucketLimiter(script_runner)
    try:
        yield
    finally:
        await redis_client.aclose()


app = FastAPI(
    title="Rate Limiter Service",
    description="Token-bucket rate limiting backed by Redis, enforced consistently across instances.",
    version="1.0.0",
    lifespan=lifespan,
)


def get_identity(request: Request) -> str:
    # In a real deployment this reads the verified user id set by auth
    # middleware after signature verification — never a raw client header
    # (see Security Review, Threat 1: identity spoofing).
    return request.headers.get("X-User-Id") or (request.client.host if request.client else "unknown")


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limit_exceeded", "message": "Too many requests."},
        headers=exc.headers,
    )


@app.get("/health")
async def health():
    return {"status": "ok", "instance": os.environ.get("INSTANCE_NAME", "unknown")}


@app.get("/api/read", dependencies=[Depends(rate_limit_dependency(POLICIES["read"], get_identity))])
async def read_endpoint():
    return {"data": "read ok", "instance": os.environ.get("INSTANCE_NAME", "unknown")}


@app.post("/api/write", dependencies=[Depends(rate_limit_dependency(POLICIES["write"], get_identity))])
async def write_endpoint():
    return {"data": "write ok", "instance": os.environ.get("INSTANCE_NAME", "unknown")}


@app.post("/api/auth", dependencies=[Depends(rate_limit_dependency(POLICIES["auth"], get_identity))])
async def auth_endpoint():
    return {"data": "auth ok", "instance": os.environ.get("INSTANCE_NAME", "unknown")}


@app.get("/metrics")
async def metrics():
    return Response(content=generate_metrics(), media_type="text/plain")
