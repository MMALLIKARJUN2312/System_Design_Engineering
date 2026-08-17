from prometheus_client import Counter, Histogram, generate_latest

rate_limit_checks_total = Counter(
    "rate_limit_checks_total",
    "Total rate limit checks performed",
    ["endpoint_class", "outcome"],  # outcome: allowed | denied
)

rate_limit_redis_failures_total = Counter(
    "rate_limit_redis_failures_total",
    "Redis failures encountered during rate limit checks",
    ["endpoint_class", "fail_mode"],  # fail_mode: open | closed
)

rate_limit_check_duration_seconds = Histogram(
    "rate_limit_check_duration_seconds",
    "Latency of the rate limit check itself (Redis round trip + Lua exec)",
    ["endpoint_class"],
    buckets=[0.0005, 0.001, 0.002, 0.005, 0.01, 0.025, 0.05, 0.1],
)


def generate_metrics() -> bytes:
    return generate_latest()
