# cache.py
# Async Redis cache with TTL+jitter, dogpile protection, and stats counters.

import os
import json
import random
import time
import asyncio
import functools
import inspect
from typing import Any, Optional, Callable, Awaitable

import redis.asyncio as redis
from redis.exceptions import ConnectionError, TimeoutError, BusyLoadingError

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_pool = redis.ConnectionPool.from_url(
    REDIS_URL,
    max_connections=int(os.getenv("REDIS_POOL_MAX", "200")),
    socket_connect_timeout=1.0,
    socket_timeout=1.5,
    health_check_interval=30,
    retry_on_timeout=True,
)
r = redis.Redis(connection_pool=_pool, decode_responses=True)

STAT_HITS   = "stats:cache_hits"
STAT_MISSES = "stats:cache_misses"
STAT_API    = "stats:api_calls"

async def incr(key: str, by: int = 1) -> None:
    try:
        await r.incrby(key, by)
    except Exception:
        pass  # fail-open

def _dump(v: Any) -> str:
    return json.dumps(v, separators=(",", ":"), ensure_ascii=False)

def _load(s: Optional[str]) -> Any:
    return None if s is None else json.loads(s)

async def cache_get(key: str) -> Optional[Any]:
    try:
        raw = await r.get(key)
        return _load(raw)
    except (ConnectionError, TimeoutError, BusyLoadingError):
        return None

async def cache_set(key: str, value: Any, ttl: int) -> None:
    try:
        await r.setex(key, ttl, _dump(value))
    except (ConnectionError, TimeoutError, BusyLoadingError):
        pass

async def cache_delete(key: str) -> None:
    try:
        await r.delete(key)
    except Exception:
        pass

def cached(
    ttl: int = 300,
    namespace: str = "",
    lock_ttl: int = 5,
    jitter_max: int = 30,
    make_key: Callable[..., str] | None = None,
):
    """
    Async-aware cache-aside decorator with:
      - TTL + jitter
      - dogpile protection via NX lock
      - global hit/miss counters in Redis
    """
    def decorator(fn: Callable[..., Any | Awaitable[Any]]):
        is_async = inspect.iscoroutinefunction(fn)

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            key_base = (make_key(*args, **kwargs) if make_key
                        else f"{fn.__module__}.{fn.__name__}:{args}:{sorted(kwargs.items())}")
            key = f"{namespace}:{key_base}" if namespace else key_base
            lock_key = f"__lock__:{key}"

            # fast path
            val = await cache_get(key)
            if val is not None:
                await incr(STAT_HITS)
                return val

            await incr(STAT_MISSES)

            # acquire short lock
            got_lock = False
            try:
                got_lock = await r.set(lock_key, "1", nx=True, ex=lock_ttl) or False
            except Exception:
                pass

            if not got_lock:
                deadline = time.time() + lock_ttl
                while time.time() < deadline:
                    await asyncio.sleep(0.02)
                    val = await cache_get(key)
                    if val is not None:
                        await incr(STAT_HITS)
                        return val
                # fall through to compute

            try:
                # double-check
                val = await cache_get(key)
                if val is not None:
                    await incr(STAT_HITS)
                    return val

                result = await fn(*args, **kwargs) if is_async else fn(*args, **kwargs)
                ttl_with_jitter = ttl + random.randint(0, jitter_max)
                await cache_set(key, result, ttl_with_jitter)
                return result
            finally:
                if got_lock:
                    try:
                        await r.delete(lock_key)
                    except Exception:
                        pass

        def sync_wrapper(*args, **kwargs):
            return asyncio.run(async_wrapper(*args, **kwargs))

        return async_wrapper if is_async else sync_wrapper
    return decorator

async def redis_ok() -> bool:
    try:
        await r.ping()
        return True
    except Exception:
        return False
