import math
import time
import uuid
from typing import Tuple
from fastapi import HTTPException, status
from loguru import logger

from app.core.redis import get_redis_client


SLIDING_WINDOW_LUA_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_limit = tonumber(ARGV[3])
local member_id = ARGV[4]

local clear_before = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)
local current_count = redis.call('ZCARD', key)

if current_count < max_limit then
    redis.call('ZADD', key, now, member_id)
    redis.call('EXPIRE', key, math.ceil(window) + 10)
    local remaining = max_limit - current_count - 1
    return {1, remaining, 0}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 1
    if #oldest >= 2 then
        local oldest_score = tonumber(oldest[2])
        retry_after = math.max(1, math.ceil(oldest_score + window - now))
    end
    redis.call('EXPIRE', key, math.ceil(window) + 10)
    return {0, 0, retry_after}
end
"""


class RedisSlidingWindowLimiter:
    """
    Sub-millisecond Redis Sorted Set (ZSet) Sliding Window Rate Limiter.
    Atomically clears expired timestamps, verifies sliding window quotas,
    and returns precise Retry-After countdowns in a single network round-trip.
    """

    def __init__(
        self,
        key_prefix: str = "rate_limit:user",
        max_requests: int = 15,
        window_seconds: int = 60,
    ) -> None:
        self.key_prefix = key_prefix
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def _get_redis_key(self, identifier: str) -> str:
        """Constructs partitioned Redis key based on prefix and client identity."""
        return f"{self.key_prefix}:{identifier}"

    async def is_allowed(self, identifier: str) -> Tuple[bool, int, int]:
        """
        Executes atomic Lua script to evaluate and record incoming request.
        Returns:
            Tuple[bool, int, int]: (is_allowed, remaining_quota, retry_after_seconds)
        """
        redis_key = self._get_redis_key(identifier)
        now = time.time()
        member_id = f"{now:.6f}:{uuid.uuid4().hex[:6]}"

        try:
            client = get_redis_client()
            res = await client.eval(
                SLIDING_WINDOW_LUA_SCRIPT,
                1,
                redis_key,
                str(now),
                str(self.window_seconds),
                str(self.max_requests),
                member_id,
            )
            is_allowed = bool(res[0] == 1)
            remaining = int(res[1])
            retry_after = int(res[2])
            return is_allowed, remaining, retry_after
        except Exception as e:
            # Fail-open design: Log warning on Redis outage without blocking legitimate traffic
            logger.error(
                f"⚠️ [RateLimiter] Redis failure for key '{redis_key}': {e}. "
                "Failing open to preserve high availability."
            )
            return True, self.max_requests, 0

    async def check_and_record(self, identifier: str) -> None:
        """
        Guards endpoint execution by validating current request against rate limits.
        Raises HTTP 429 Too Many Requests with Retry-After header if limit exceeded.
        """
        is_allowed, remaining, retry_after = await self.is_allowed(identifier)

        if not is_allowed:
            logger.warning(
                f"🚨 [RateLimiter] Rate limit exceeded for '{identifier}' "
                f"({self.max_requests} req / {self.window_seconds}s). Retry-After: {retry_after}s"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Too many requests. Limit is {self.max_requests} requests "
                    f"per {self.window_seconds} seconds. Please retry after {retry_after}s."
                ),
                headers={"Retry-After": str(retry_after)},
            )

        logger.debug(
            f"✅ [RateLimiter] Allowed '{identifier}' (Remaining: {remaining}/{self.max_requests})"
        )

    async def reset(self, identifier: str) -> None:
        """Cleans rate limiter state for specific identifier (useful for test isolation)."""
        redis_key = self._get_redis_key(identifier)
        try:
            client = get_redis_client()
            await client.delete(redis_key)
            logger.debug(f"🧹 [RateLimiter] Reset key '{redis_key}'")
        except Exception as e:
            logger.warning(f"Failed to reset rate limiter key '{redis_key}': {e}")
