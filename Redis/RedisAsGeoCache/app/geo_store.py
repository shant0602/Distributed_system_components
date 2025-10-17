import os, json, random
from typing import Optional, List, Dict, Tuple
import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

CACHE_TTL = int(os.getenv("GEO_CACHE_TTL", "120"))
TMP_TTL   = int(os.getenv("GEO_TMP_TTL", "15"))
QUERY_QUANT = float(os.getenv("GEO_QUERY_QUANT", "0.0005"))

GEO_KEY         = "poi:geo"
POI_HASH        = "poi:{id}"
TAG_SET         = "poi:tag:{tag}"
CAT_SET         = "poi:cat:{cat}"
CACHE_NEARBY    = "poi:cache:nearby:{lat},{lon}:{r}:{lim}:{cat}:{tag}"
STAT_QUERIES    = "stats:geo:queries"
STAT_CACHE_HIT  = "stats:geo:cache_hits"
STAT_CACHE_MISS = "stats:geo:cache_misses"
STAT_WRITES     = "stats:geo:writes"
STAT_SCANNED    = "stats:geo:candidates_scanned"

_pool = redis.ConnectionPool.from_url(
    REDIS_URL,
    max_connections=int(os.getenv("REDIS_POOL_MAX", "300")),
    socket_connect_timeout=1.0,
    socket_timeout=1.5,
    health_check_interval=30,
    retry_on_timeout=True,
)
r = redis.Redis(connection_pool=_pool, decode_responses=True)

def _dump(x): return json.dumps(x, separators=(",", ":"), ensure_ascii=False)
def _load(s): return None if s is None else json.loads(s)
def _jitter(ttl: int, max_j: int = 20) -> int: return ttl + random.randint(0, max_j)

def _q(v: float) -> float:
    q = QUERY_QUANT
    return round(round(v / q) * q, 6)

def _cache_key(lat: float, lon: float, radius_km: float, limit: int,
               category: Optional[str], tag: Optional[str]) -> str:
    return CACHE_NEARBY.format(
        lat=f"{_q(lat):.6f}", lon=f"{_q(lon):.6f}",
        r=f"{radius_km:.2f}", lim=limit,
        cat=(category or "_"), tag=(tag or "_")
    )

async def incr(key: str, by: int = 1):
    try:
        await r.incrby(key, by)
    except Exception:
        pass

# ----------------- Core writes -----------------

async def upsert_poi(poi: Dict) -> str:
    pid = poi["id"]
    lat, lon = float(poi["lat"]), float(poi["lon"])
    tags = poi.get("tags") or []
    cat  = poi.get("category")

    # Validate ranges early (helps catch bad inputs)
    if not (-85.05112878 <= lat <= 85.05112878):
        raise ValueError(f"lat out of range: {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"lon out of range: {lon}")

    pipe = r.pipeline()
    # robust GEOADD
    pipe.execute_command("GEOADD", GEO_KEY, lon, lat, pid)
    pipe.hset(POI_HASH.format(id=pid), mapping={
        "name": poi["name"],
        "lat": lat, "lon": lon,
        "category": cat or "",
        "tags": _dump(tags),
        "metadata": _dump(poi.get("metadata") or {})
    })
    if cat:
        pipe.sadd(CAT_SET.format(cat=cat), pid)
    for t in tags:
        pipe.sadd(TAG_SET.format(tag=t), pid)
    await pipe.execute()
    await incr(STAT_WRITES)
    return pid

async def delete_poi(pid: str):
    pipe = r.pipeline()
    pipe.zrem(GEO_KEY, pid)
    pipe.delete(POI_HASH.format(id=pid))
    await pipe.execute()

async def get_poi(pid: str) -> Optional[Dict]:
    hash_key = POI_HASH.format(id=pid)
    print(f"DEBUG: Getting POI with key: {hash_key}")
    h = await r.hgetall(hash_key)
    print(f"DEBUG: hgetall returned: {h}")
    print(f"DEBUG: Type of h: {type(h)}")
    if not h:
        print("DEBUG: Hash is empty, returning None")
        return None
    h = { (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v) for k, v in h.items() }
    print(f"DEBUG: lat value: {h.get('lat')} (type: {type(h.get('lat'))})")
    print(f"DEBUG: lon value: {h.get('lon')} (type: {type(h.get('lon'))})")
    
    return {
        "id": pid,
        "name": h.get("name"),
        "lat": float(h.get("lat")),
        "lon": float(h.get("lon")),
        "category": (h.get("category") or "") or None,
        "tags": _load(h.get("tags") or "[]"),
        "metadata": _load(h.get("metadata") or "{}"),
    }

# ----------------- GEO query -----------------

async def _geosearch_candidates(lat: float, lon: float, radius_km: float, count: int):
    """
    Use GEOSEARCH (Redis 6.2+) via redis-py. Normalize results across RESP2/RESP3
    and redis-py versions. Fallback to GEORADIUS on any exception.
    Returns list of (member:str, dist_km:float) sorted ASC by distance.
    """
    try:
        rows = await r.geosearch(
            GEO_KEY,
            fromlonlat=(lon, lat),
            byradius=(radius_km, "km"),
            withdist=True,
            sort="ASC",
            count=count,
        )
        out: list[tuple[str, float]] = []
        for row in (rows or []):
            member = None
            dist = None
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                member, dist = row[0], row[1]
            elif isinstance(row, dict):  # RESP3 style
                member = row.get("member") or row.get(b"member")
                dist = row.get("dist") or row.get(b"dist")
            else:
                continue
            if isinstance(member, bytes):
                member = member.decode()
            out.append((member, float(dist)))
        return out
    except Exception:
        rows = await r.execute_command(
            "GEORADIUS", GEO_KEY, lon, lat, radius_km, "km", "WITHDIST", "ASC", "COUNT", count
        )
        out: list[tuple[str, float]] = []
        for row in (rows or []):
            mid = row[0].decode() if isinstance(row[0], bytes) else row[0]
            out.append((mid, float(row[1])))
        return out

async def nearby(lat: float, lon: float, radius_km: float, limit: int,
                 category: Optional[str] = None, tag: Optional[str] = None) -> List[Dict]:
    await incr(STAT_QUERIES)
    ckey = _cache_key(lat, lon, radius_km, limit, category, tag)
    print(f"DEBUG[nearby]: lat={lat} lon={lon} r_km={radius_km} limit={limit} cat={category} tag={tag}")
    print(f"DEBUG[nearby]: cache_key={ckey}")
    cached = _load(await r.get(ckey))
    if cached is not None:
        await incr(STAT_CACHE_HIT)
        print(f"DEBUG[nearby]: cache HIT items={len(cached)}")
        return cached

    await incr(STAT_CACHE_MISS)
    print("DEBUG[nearby]: cache MISS")
    count_hint = max(limit * 5, limit + 20)
    candidates = await _geosearch_candidates(lat, lon, radius_km, count_hint)
    print(f"DEBUG[nearby]: candidates_found={len(candidates)} (hint={count_hint})")
    await incr(STAT_SCANNED, by=len(candidates))

    filtered: List[Tuple[str, float]] = []
    for mid, dist in candidates:
        if category and not await r.sismember(CAT_SET.format(cat=category), mid):
            continue
        if tag and not await r.sismember(TAG_SET.format(tag=tag), mid):
            continue
        filtered.append((mid, dist))
        if len(filtered) >= limit:
            break

    out: List[Dict] = []
    if filtered:
        print(f"DEBUG[nearby]: filtered_count={len(filtered)}")
        pipe = r.pipeline()
        for mid, _ in filtered:
            pipe.hgetall(POI_HASH.format(id=mid))
        raw = await pipe.execute()
        for (mid, dist), h in zip(filtered, raw):
            if not h:
                continue
            # Normalize keys and values to str consistently (handles bytes in either)
            h = {
                (k.decode() if isinstance(k, bytes) else k):
                (v.decode() if isinstance(v, bytes) else v)
                for k, v in h.items()
            }
            # Ensure member id is a str
            if isinstance(mid, bytes):
                mid = mid.decode()
            out.append({
                "id": mid,
                "name": h.get("name"),
                "lat": float(h.get("lat")),
                "lon": float(h.get("lon")),
                "category": (h.get("category") or "") or None,
                "tags": _load(h.get("tags") or "[]"),
                "metadata": _load(h.get("metadata") or "{}"),
                "distance_km": round(dist, 3),
            })
    else:
        print("DEBUG[nearby]: filtered_count=0")

    await r.setex(ckey, _jitter(CACHE_TTL), _dump(out))
    print(f"DEBUG[nearby]: returning items={len(out)} and cached for ~{CACHE_TTL}s (jittered)")
    return out

# ----------------- Health & Stats -----------------

async def redis_ok() -> bool:
    try:
        await r.ping()
        return True
    except Exception:
        return False

async def stats() -> Dict:
    pipe = r.pipeline()
    pipe.get(STAT_QUERIES)
    pipe.get(STAT_CACHE_HIT)
    pipe.get(STAT_CACHE_MISS)
    pipe.get(STAT_WRITES)
    pipe.get(STAT_SCANNED)
    q, h, m, w, s = await pipe.execute()
    to_i = lambda x: int(x or 0)
    total = to_i(h) + to_i(m)
    return {
        "queries": to_i(q),
        "cache_hits": to_i(h),
        "cache_misses": to_i(m),
        "hit_ratio": (to_i(h)/total) if total else None,
        "writes": to_i(w),
        "candidates_scanned": to_i(s),
    }
