from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from models import POIUpsert, POIResult
from geo_store import upsert_poi, delete_poi, get_poi, nearby, redis_ok, stats

app = FastAPI(title="Redis GEO Proximity Service", version="1.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
async def healthz():
    return {"redis_ok": await redis_ok()}

@app.post("/poi")
async def create_or_update_poi(poi: POIUpsert):
    try:
        pid = await upsert_poi(poi.model_dump())
        return JSONResponse({"id": pid, "ok": True})
    except Exception as e:
        # include message for visibility
        raise HTTPException(status_code=500, detail=f"upsert_failed:{type(e).__name__}:{e}")

@app.get("/poi/nearby", response_model=List[POIResult])
async def poi_nearby(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_km: float = Query(5.0, gt=0),
    limit: int = Query(20, gt=0, le=200),
    category: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
):
    try:
        res = await nearby(lat=lat, lon=lon, radius_km=radius_km, limit=limit,
                           category=category, tag=tag)
        # Always return a JSON array (never None)
        return res or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"nearby_failed:{type(e).__name__}")

@app.get("/poi/{poi_id}", response_model=POIResult)
async def read_poi(poi_id: str):
    p = await get_poi(poi_id)
    if not p:
        raise HTTPException(status_code=404, detail="POI not found")
    p["distance_km"] = 0.0
    return p

@app.delete("/poi/{poi_id}")
async def remove_poi(poi_id: str):
    await delete_poi(poi_id)
    return JSONResponse({"ok": True})

@app.get("/stats")
async def get_stats():
    return await stats()
