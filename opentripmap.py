# opentripmap.py
import os
import httpx
from typing import List, Dict, Any

OTM_KEY = os.getenv("OPENTRIPMAP_API_KEY")
GEONAME_URL = "https://api.opentripmap.com/0.1/en/places/geoname"
RADIUS_URL = "https://api.opentripmap.com/0.1/en/places/radius"
BASE = "https://api.opentripmap.com/0.1/en/places"

async def geocode_city(city: str):
    """Return (lat, lon) or (None, None)"""
    if not OTM_KEY:
        return None, None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(GEONAME_URL, params={"name": city, "apikey": OTM_KEY})
            r.raise_for_status()
            j = r.json()
            return j.get("lat"), j.get("lon")
    except Exception:
        return None, None

async def get_mindful_places(lat: float, lon: float, radius: int = 2000, limit: int = 5) -> List[Dict[str, Any]]:
    """Return list of nearby attractions from OpenTripMap (normalized)"""
    if not OTM_KEY:
        return []
    try:
        params = {"radius": radius, "lon": lon, "lat": lat, "limit": limit, "apikey": OTM_KEY}
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(RADIUS_URL, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return []

    out = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        out.append({
            "title": props.get("name") or props.get("kinds", "Attraction"),
            "kinds": props.get("kinds"),
            "rate": props.get("rate"),
            "source": "opentripmap",
            "xid": props.get("xid"),
        })
    return out
