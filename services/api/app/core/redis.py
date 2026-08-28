"""Shared Redis client plus a fixed-window rate limiter."""

from redis.asyncio import Redis, from_url

from app.core.config import settings
from app.core.errors import RateLimitError

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = from_url(settings.REDIS_URL, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def enforce_rate_limit(key: str, *, limit: int, window_seconds: int) -> None:
    """Fixed-window counter. Raises RateLimitError once `limit` is exceeded.

    Fixed window (not sliding) is intentional: it is one INCR, and the burst it
    allows at a window boundary is harmless for OTP and login endpoints.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return

    redis = get_redis()
    full_key = f"ratelimit:{key}"
    count = await redis.incr(full_key)
    if count == 1:
        await redis.expire(full_key, window_seconds)
    if count > limit:
        ttl = await redis.ttl(full_key)
        raise RateLimitError(
            "Too many attempts. Please try again shortly.",
            details={"retry_after_seconds": max(ttl, 1)},
        )
