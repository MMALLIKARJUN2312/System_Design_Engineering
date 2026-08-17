-- Atomic token-bucket check-and-consume.
-- Runs inside Redis's single-threaded script execution, so the
-- read-refill-compare-write sequence below can never race with itself
-- across concurrent callers hitting the same key.
--
-- KEYS[1] = redis key (one Hash per identity+endpoint_class)
-- ARGV[1] = capacity (max tokens the bucket can hold)
-- ARGV[2] = refill_rate (tokens added per second; must be > 0 -- the TTL
--           calculation below divides by it)
-- ARGV[3] = now (unix timestamp, float seconds)
-- ARGV[4] = cost (tokens this request consumes, usually 1)
--
-- Returns: { allowed (0 or 1), tokens_remaining }

local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local bucket = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

-- Lazy refill: reconstruct elapsed time since last touch instead of
-- ticking every bucket on a schedule.
local elapsed = math.max(0, now - last_refill)
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
if tokens >= cost then
    tokens = tokens - cost
    allowed = 1
end

redis.call("HMSET", key, "tokens", tokens, "last_refill", now)

-- Idle buckets expire instead of living forever in memory.
local ttl = math.max(1, math.ceil((capacity / refill_rate) * 2))
redis.call("EXPIRE", key, ttl)

return { allowed, tostring(tokens) }
