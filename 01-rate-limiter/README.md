# Project 1 — Production-Grade Rate Limiter

A token-bucket rate limiter enforced consistently across multiple stateless
app instances via a shared Redis backend and an atomic Lua script.

Full design writeup (problem statement, capacity planning, algorithm
comparison, security review, scaling plan) lives in the conversation this
project was built from — this README covers only how to run it.

## Why this exists

A per-process in-memory counter breaks the moment you run more than one app
server: a load balancer spreads one user's requests across instances, and
each instance only sees (and limits) its own slice of that traffic. The
fix is centralizing the counter in Redis and making the
check-and-decrement atomic (a Lua script), so concurrent requests across
any number of app instances can't race each other into over-counting.

Built on **FastAPI** (async, ASGI) rather than Flask specifically so the
async Redis client doesn't block the event loop under load, and so the
API contract is self-documenting via the auto-generated Swagger UI.

## Layout

```
limiter.py       Core token-bucket decision logic (allow/deny), no HTTP knowledge
redis_client.py  Thin async Redis transport: connection + compiled Lua script
middleware.py    FastAPI dependency: identity resolution, headers, 429 handling
config.py        Per-endpoint-class policies (capacity, refill rate, fail-open/closed)
metrics.py       Prometheus counters/histograms
app.py           FastAPI app wiring it all together (/api/read, /api/write, /api/auth)
                 + lifespan-managed Redis client + auto Swagger docs at /docs
scripts/token_bucket.lua       The atomic check-and-consume script
scripts/verify_shared_limit.sh End-to-end proof that the limit is shared across instances
test_limiter.py                   Unit tests (mocked Redis) — fail-open/closed branching
test_token_bucket_integration.py  Integration tests (real Redis) — bucket math correctness
test_concurrency.py               Proves the race condition is closed under concurrent load
test_app.py                       End-to-end tests against the FastAPI app itself
```

## Run it locally

```bash
docker compose up -d --build
curl http://localhost:8080/api/read
curl -X POST http://localhost:8080/api/write -H "X-User-Id: alice"
```

Or without Docker, against a local Redis:

```bash
pip install -r requirements.txt
redis-server &
REDIS_HOST=localhost uvicorn app:app --reload
```

Then open **http://localhost:8000/docs** for the interactive Swagger UI
(generated automatically from the route definitions — no extra work
required to keep it in sync with the code).

Every response carries `X-RateLimit-Limit` / `X-RateLimit-Remaining`
headers. Exceeding a bucket's capacity returns `429` with a
`Retry-After` header.

Prove the limit is actually shared across the three load-balanced app
instances (not just working by luck on one instance):

```bash
bash scripts/verify_shared_limit.sh
```

## Run the tests

```bash
pip install -r requirements.txt

# No external dependencies:
pytest test_limiter.py -v

# Needs a local Redis (or: docker run -p 6379:6379 redis:7-alpine)
pytest test_token_bucket_integration.py test_concurrency.py test_app.py -v
```

## Policies

| Endpoint class | Capacity | Refill rate | On Redis outage |
|---|---|---|---|
| `read` | 100 | 10/sec | fail open (allow) |
| `write` | 20 | 2/sec | fail open (allow) |
| `auth` | 5 | 0.1/sec | fail closed (deny) |

`auth` fails closed deliberately: unlimited login attempts during a Redis
outage is an active brute-force vulnerability, not just a degraded
experience. Everything else fails open so a Redis blip degrades to
"unlimited traffic" rather than taking the API down.
