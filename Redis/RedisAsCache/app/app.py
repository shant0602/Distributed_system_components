# app.py
# FastAPI weather service using Redis cache
# - /weather supports ?city=... OR ?lat=...&lon=...
# - City path: cached with TTL + jitter + dogpile + stale-on-error
# - Lat/Lon path: bypasses geocoding; robust 502 mapping on upstream errors
# - /stats and /healthz

import os
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from cache import (
    cached,
    cache_get,
    cache_set,
    incr,
    STAT_API,
    STAT_HITS,
    STAT_MISSES,
    redis_ok,
    r,
)
from provider_openmeteo import get_weather_by_city, current_weather

app = FastAPI(title="Weather + Redis Cache Service", version="1.1.1")

# ---- Config ----
FRESH_TTL = int(os.getenv("WEATHER_TTL", "300"))
STALE_TTL = 24 * 3600

# ---- Cache keys ----
def weather_key(city: str) -> str:
    return f"weather:v1:city:{city.strip().lower()}"

def weather_stale_key(city: str) -> str:
    return f"weather:v1:stale:{city.strip().lower()}"

# ---- Cached city fetch (counts upstream calls on miss) ----
@cached(ttl=FRESH_TTL, lock_ttl=5, jitter_max=30, make_key=weather_key)
async def _fetch_weather_city(city: str):
    await incr(STAT_API)  # only on real upstream call
    data = await get_weather_by_city(city)
    if data is None:
        # serve stale if available
        stale = await cache_get(weather_stale_key(city))
        if stale:
            stale["_stale"] = True
            return stale
        raise HTTPException(status_code=502, detail=f"Upstream failure for city '{city}'. Try again.")
    # refresh stale copy
    await cache_set(weather_stale_key(city), data, STALE_TTL)
    return data

# ---- Endpoints ----
@app.get("/weather")
async def weather(
    city: str = Query(..., description="City name, e.g., 'San Jose'"),
):
    """
    Get weather for a city.
    Example: ?city=San%20Jose
    """
    result = await _fetch_weather_city(city)
    return JSONResponse(result)

@app.get("/stats")
async def stats():
    pipe = r.pipeline()
    pipe.get(STAT_HITS)
    pipe.get(STAT_MISSES)
    pipe.get(STAT_API)
    hits, misses, api_calls = await pipe.execute()

    hits = int(hits or 0)
    misses = int(misses or 0)
    api_calls = int(api_calls or 0)
    return {
        "cache_hits": hits,
        "cache_misses": misses,
        "api_calls": api_calls,
        "avoided_api_calls": hits,
        "hit_ratio": (hits / (hits + misses)) if (hits + misses) else None,
    }

@app.get("/healthz")
async def healthz():
    return {"redis_ok": await redis_ok(), "provider_ok": True}
