from __future__ import annotations

import math
import os
import re
from typing import Any

import httpx
from dotenv import load_dotenv

from weather_openmeteo import get_lat_lon_from_city

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_TABLE = os.getenv("SUPABASE_PLACES_TABLE", "voyayaha_places")


def configuration_status() -> dict[str, bool]:
    return {
        "supabase_url": bool(SUPABASE_URL),
        "supabase_service_role_key": bool(SUPABASE_SERVICE_ROLE_KEY),
    }


def _distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _words(value: str) -> list[str]:
    return [x for x in re.findall(r"[a-z0-9]+", value.lower()) if len(x) >= 3]


def _headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Accept": "application/json",
    }


async def search_curated_places(
    location: str,
    query: str = "",
    radius_km: float = 100,
    limit: int = 3,
    center: tuple[float, float] | None = None,
) -> list[dict[str, Any]]:
    """Return published, verified Voyayaha places near the requested city.

    This is deliberately a SECONDARY source. The social discovery engine is
    still responsible for first-priority recommendations. The database only
    fills missing slots or provides curated places when social evidence is thin.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return []

    if center is None:
        lat, lon = await __import__("asyncio").to_thread(get_lat_lon_from_city, location)
    else:
        lat, lon = center
    if lat is None or lon is None:
        return []

    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
    params = {
        "select": "id,name,slug,city,region,country,latitude,longitude,category,description,best_for,image_url,source_url,source,verified,published,featured",
        "published": "eq.true",
        "verified": "eq.true",
        "limit": "1000",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, params=params, headers=_headers())
            response.raise_for_status()
            rows = response.json()
    except Exception as exc:
        print("Supabase places error:", repr(exc))
        return []

    if not isinstance(rows, list):
        return []

    query_words = _words(query)
    location_words = _words(location)
    scored: list[dict[str, Any]] = []
    for row in rows:
        try:
            rlat = float(row.get("latitude"))
            rlon = float(row.get("longitude"))
        except (TypeError, ValueError):
            continue
        distance = _distance_km(float(lat), float(lon), rlat, rlon)
        if distance > float(radius_km):
            continue

        searchable = " ".join(str(row.get(k) or "") for k in (
            "name", "city", "region", "country", "category", "description", "best_for"
        )).lower()
        score = 0.0
        for word in query_words:
            if word in searchable:
                score += 3.0
        for word in location_words:
            if word in searchable:
                score += 1.5
        if bool(row.get("featured")):
            score += 1.0
        # Prefer closer curated places when relevance is otherwise similar.
        score += max(0.0, 10.0 * (1.0 - distance / max(float(radius_km), 1.0)))

        scored.append({
            "id": row.get("id"),
            "name": str(row.get("name") or "Voyayaha place"),
            "slug": row.get("slug"),
            "city": row.get("city"),
            "region": row.get("region"),
            "country": row.get("country"),
            "latitude": rlat,
            "longitude": rlon,
            "distance_km": round(distance, 1),
            "category": row.get("category") or "Hidden place",
            "description": row.get("description") or "",
            "best_for": row.get("best_for") or "",
            "image_url": row.get("image_url"),
            "source_url": row.get("source_url"),
            "source": row.get("source") or "Voyayaha",
            "featured": bool(row.get("featured")),
            "database_score": round(score, 1),
        })

    scored.sort(key=lambda x: (-x["database_score"], x["distance_km"]))
    return scored[: max(1, min(int(limit), 3))]


async def database_health() -> dict[str, Any]:
    result: dict[str, Any] = {
        "database_version": "1.0",
        "configuration": configuration_status(),
        "table": SUPABASE_TABLE,
        "reachable": False,
    }
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        result["message"] = "Add SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to Render environment variables."
        return result
    try:
        url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                url,
                params={"select": "id", "limit": "1"},
                headers=_headers(),
            )
        result["reachable"] = response.is_success
        if not response.is_success:
            result["status_code"] = response.status_code
            result["message"] = response.text[:500]
        else:
            result["message"] = "Supabase place database is reachable."
    except Exception as exc:
        result["message"] = f"Supabase connection failed: {exc}"
    return result
