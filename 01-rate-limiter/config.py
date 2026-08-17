from limiter import FailMode, RateLimitPolicy

# General endpoints fail OPEN: a Redis outage degrades to "unlimited" rather
# than taking the whole API down with it.
#
# `auth` fails CLOSED: unlimited login attempts during a Redis outage is an
# active brute-force vulnerability, not just an inconvenience, so we'd
# rather reject traffic than silently disable login throttling.
POLICIES = {
    "read": RateLimitPolicy("read", capacity=100, refill_rate=10, fail_mode=FailMode.OPEN),
    "write": RateLimitPolicy("write", capacity=20, refill_rate=2, fail_mode=FailMode.OPEN),
    "auth": RateLimitPolicy("auth", capacity=5, refill_rate=0.1, fail_mode=FailMode.CLOSED),
}
