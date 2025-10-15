# provider_openmeteo.py
# Open-Meteo based provider: geocode city -> current weather.

from typing import Dict, Any, Optional
import httpx
import asyncio

HTTP_TIMEOUT = 2.0

async def _get_json(client: httpx.AsyncClient, url: str, params: dict) -> Optional[dict]:
    try:
        resp = await client.get(url, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None

async def geocode_city(client: httpx.AsyncClient, city: str) -> Optional[Dict[str, float]]:
    data = await _get_json(
        client,
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": city, "count": 1, "language": "en", "format": "json"},
    )
    if not data or not data.get("results"):
        return None
    top = data["results"][0]
    return {"lat": top["latitude"], "lon": top["longitude"], "name": top["name"], "country": top.get("country_code")}

async def current_weather(client: httpx.AsyncClient, lat: float, lon: float) -> Optional[Dict[str, Any]]:
    data = await _get_json(
        client,
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": lat,
            "longitude": lon,
            "current_weather": True,
            "temperature_unit": "celsius",
            "windspeed_unit": "kmh",
            "precipitation_unit": "mm",
        },
    )
    if not data or "current_weather" not in data:
        return None
    return data["current_weather"]

async def get_weather_by_city(city: str) -> Optional[Dict[str, Any]]:
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(http2=True) as client:
                loc = await geocode_city(client, city)
                if not loc:
                    return None
                cw = await current_weather(client, loc["lat"], loc["lon"])
                if not cw:
                    return None
                cw["city"] = loc["name"]
                cw["country"] = loc.get("country")
                return cw
        except Exception:
            if attempt == 1:
                return None
            await asyncio.sleep(0.1)
    return None
