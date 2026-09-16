from __future__ import annotations

import json
import os
from datetime import date
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from hotels import search_hotels
from experiences import get_combined_experiences
from llm import generate_itinerary
from weather import get_weather_and_risk
from villageexperiences import get_village_experiences
from weather_openmeteo import get_weather_16_days, get_lat_lon_from_city, get_aqi
from traveler_advice import build_traveler_advice
from traffic_tomtom import get_traffic_status
from social import get_youtube_posts, get_reddit_posts
from voyayaha_hidden_llm import generate_hidden_itinerary
from voyayaha_hidden_social import get_hidden_social
from social_discovery import discover_social_places

load_dotenv()

APP_VERSION = "2.0.0"
app = FastAPI(title="Voyayaha Travel API", version=APP_VERSION)

# Browser requests normally go through the frontend /api proxy, but direct
# requests are also supported. Configure production origins in Render with
# CORS_ORIGINS (comma separated). Wildcard is only used when explicitly set.
DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "https://voyayaha.com",
    "https://www.voyayaha.com",
    "https://voyayaha.lovable.app",
]
_env_origins = [x.strip().rstrip("/") for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()]
ALLOWED_ORIGINS = _env_origins or DEFAULT_ORIGINS
allow_credentials = "*" not in ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "Origin", "X-Requested-With"],
    expose_headers=["Content-Type"],
    max_age=86400,
)

# ---------- schemas ----------
class ExperienceRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    location: str = Field(min_length=1)
    budget: str = ""
    activity: str = ""
    duration: str = "full_day"
    motivation: str = ""
    num_days: int = Field(default=1, ge=1, le=30)

    @field_validator("duration", mode="before")
    @classmethod
    def normalize_duration(cls, value: Any) -> str:
        s = str(value or "full_day").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {"halfday": "half_day", "fullday": "full_day", "multiday": "multi_day"}
        return aliases.get(s, s)

class ItineraryRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    location: str = Field(min_length=1)
    budget: str = ""
    activity: str = ""
    duration: str = "full_day"
    motivation: str = ""
    num_days: int = Field(default=1, ge=1, le=30)

class ChatMessage(BaseModel):
    role: str = "user"
    content: str = ""

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    location: str = ""
    message: str = ""
    prompt: str = ""
    messages: list[ChatMessage] = Field(default_factory=list)
    budget: str = ""
    activity: str = ""
    duration: str = "full_day"
    motivation: str = ""
    num_days: int = Field(default=1, ge=1, le=30)

# ---------- helpers ----------
def _safe_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return []
    return []

def _normalise_stop(item: Any, day: int = 1) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"day": day, "title": "Explore", "intro": str(item or ""), "top_places": []}
    places = item.get("top_places") or item.get("topPlaces") or item.get("places") or []
    if not isinstance(places, list):
        places = []
    clean_places = []
    for p in places[:3]:
        if isinstance(p, dict):
            clean_places.append({
                "name": str(p.get("name") or p.get("title") or "Local place"),
                "tip": str(p.get("tip") or p.get("description") or ""),
            })
        else:
            clean_places.append({"name": str(p), "tip": ""})
    return {
        "day": int(item.get("day") or day),
        "title": str(item.get("title") or item.get("name") or "Explore"),
        "intro": str(item.get("intro") or item.get("description") or ""),
        "top_places": clean_places,
    }

def _fallback_itinerary(location: str, days: int, per_day: int) -> list[dict[str, Any]]:
    templates = [
        ("Local discovery", "Start with a relaxed walk through a central neighbourhood.", "Ask a local for a quiet breakfast or market."),
        ("Nature & views", "Spend time outdoors at a nearby scenic or green place.", "Go early for cooler weather and fewer crowds."),
        ("Culture & heritage", "Explore a historical, cultural or community-led place.", "Check opening days before travelling."),
        ("Food & local life", "Try a regional dish and spend time in a local market or café.", "Choose a busy local spot for fresher turnover."),
        ("Slow evening", "End the day somewhere calm with a sunset or neighbourhood stroll.", "Keep the evening flexible for local discoveries."),
    ]
    out = []
    idx = 0
    for d in range(1, days + 1):
        for _ in range(per_day):
            title, intro, tip = templates[idx % len(templates)]
            out.append({
                "day": d, "title": f"{title} in {location}",
                "intro": intro,
                "top_places": [{"name": f"{location} local highlight", "tip": tip}],
            })
            idx += 1
    return out

def _itinerary_prompt(data: ExperienceRequest, days: int, per_day: int) -> str:
    total = days * per_day
    return f"""
You are Voyayaha's travel planning assistant.
Destination: {data.location}
Budget: {data.budget or "not specified"}
Activity: {data.activity or "mixed"}
Motivation: {data.motivation or "explore"}
Trip duration: {days} day(s).

Return ONLY a JSON array containing exactly {total} objects.
Each object must have: day (integer), title (string), intro (string), top_places (array).
Each top_places item must have name and tip.
Use real places in or near {data.location}. Do not invent businesses or attractions.
Distribute objects across days 1..{days}; exactly {per_day} objects per day.
"""

async def _safe_await(coro, fallback):
    try:
        return await coro
    except Exception as exc:
        print("optional service error:", repr(exc))
        return fallback

# ---------- health ----------
@app.get("/")
async def root():
    return {"status": "ok", "service": "Voyayaha backend", "version": APP_VERSION}

@app.get("/health")
async def health():
    return {"status": "healthy", "version": APP_VERSION}

@app.get("/api/health")
async def api_health():
    return await health()

# ---------- itinerary / chat ----------
@app.post("/chat/experiences")
async def chat_experiences(data: ExperienceRequest):
    days = 1 if data.duration in {"half_day", "full_day"} else max(1, data.num_days)
    per_day = 3 if days == 1 else 2
    expected = days * per_day
    try:
        raw = generate_itinerary(_itinerary_prompt(data, days, per_day))
        items = _safe_json(raw)
        if not isinstance(items, list):
            items = []
        stops = [_normalise_stop(x, (i // per_day) + 1) for i, x in enumerate(items[:expected])]
    except Exception as exc:
        print("itinerary error:", repr(exc))
        stops = []
    if len(stops) < expected:
        fallback = _fallback_itinerary(data.location, days, per_day)
        stops.extend(fallback[len(stops):expected])
    return {
        "stops": stops,
        "itinerary": stops,
        "data": stops,
        "meta": {"location": data.location, "days": days, "count": len(stops)},
    }

@app.post("/itinerary")
async def itinerary(data: ItineraryRequest):
    return await chat_experiences(ExperienceRequest(**data.model_dump()))

@app.post("/api/itinerary")
async def api_itinerary(data: ItineraryRequest):
    return await itinerary(data)

@app.post("/chat")
async def chat(data: ChatRequest):
    prompt = data.prompt or data.message or (data.messages[-1].content if data.messages else "")
    req = ExperienceRequest(
        location=data.location or "",
        budget=data.budget, activity=data.activity,
        duration=data.duration, motivation=prompt or data.motivation,
        num_days=data.num_days,
    )
    return await chat_experiences(req)

# ---------- hidden ----------
@app.get("/chat/experiences-hidden")
async def hidden_experiences(location: str, query: str = "", limit: int = Query(3, ge=1, le=10)):
    results = await _safe_await(
        __import__("asyncio").to_thread(generate_hidden_itinerary, location, query, limit), []
    )
    return {"stops": results if isinstance(results, list) else []}

@app.get("/hidden-experiences")
async def hidden_experiences_alias(location: str, query: str = "", limit: int = Query(3, ge=1, le=10)):
    return await hidden_experiences(location, query, limit)

@app.get("/social-hidden")
async def social_hidden(location: str = "Mumbai", query: str = "", limit: int = Query(3, ge=1, le=10)):
    return await _safe_await(get_hidden_social(location, query, limit), [])

@app.get("/social-discovery/health")
async def social_discovery_health():
    """Non-secret deployment check for the Hidden Places discovery service."""
    from social_discovery import _configuration_status
    return {
        "discovery_version": "3.1-global-place-gated",
        "configuration": _configuration_status(),
        "message": "Keys are never returned; booleans only show whether the required environment variables are present.",
    }

@app.get("/social-discovery")
async def social_discovery(
    location: str = Query(..., min_length=1),
    query: str = "",
    radius_km: float = Query(100, ge=1, le=250),
    limit: int = Query(3, ge=1, le=3),
):
    """Research Reddit + YouTube, verify candidate coordinates, and return the top 3 within radius."""
    return await _safe_await(
        discover_social_places(location, query, radius_km, limit),
        {"location": location, "radius_km": radius_km, "results": [], "degraded": True},
    )

@app.get("/api/social-discovery")
async def api_social_discovery(
    location: str = Query(..., min_length=1),
    query: str = "",
    radius_km: float = Query(100, ge=1, le=250),
    limit: int = Query(3, ge=1, le=3),
):
    return await social_discovery(location, query, radius_km, limit)

# ---------- experiences / village ----------
@app.get("/experiences")
async def experiences(location: str, query: str = "tourist"):
    result = await _safe_await(get_combined_experiences(location, query), None)
    return result or {"weather": {"summary": "Unknown", "temperature_c": None, "indoor_preferred": False}, "indoor_only": False, "yelp": [], "geoapify": []}

@app.get("/village/experiences")
async def village_experiences(location: str = Query(..., min_length=1)):
    result = await _safe_await(get_village_experiences(location), None)
    return result or {"location": location, "latitude": None, "longitude": None, "count": 0, "experiences": []}

# ---------- hotels ----------
@app.get("/hotels")
async def hotels(city: str, check_in: str = "", check_out: str = "", limit: int = Query(6, ge=1, le=20)):
    result = await _safe_await(search_hotels(city, check_in, check_out, limit), [])
    return {"city": city, "hotels": result or [], "results": result or []}

# ---------- weather ----------
@app.get("/weather")
async def weather(location: str):
    result = await _safe_await(get_weather_and_risk(location), None)
    return result or {"location": location, "summary": "Weather unavailable", "temperature_c": None, "indoor_preferred": False}

# ---------- social ----------
@app.get("/social")
async def social(location: str = "Mumbai", limit: int = Query(5, ge=1, le=20)):
    import asyncio
    youtube, reddit = await asyncio.gather(
        _safe_await(get_youtube_posts(location, limit), []),
        _safe_await(get_reddit_posts(location, limit), []),
    )
    return youtube + reddit

@app.get("/trends")
async def trends(location: str = "Pune"):
    return await _safe_await(get_reddit_posts(f"{location} travel OR {location} places OR {location} itinerary", 8), [])

# ---------- travel intel ----------
@app.get("/travel-intel")
async def travel_intel(city: str):
    lat, lon = await _safe_await(__import__("asyncio").to_thread(get_lat_lon_from_city, city), (None, None))
    if lat is None or lon is None:
        return {
            "city": city,
            "coordinates": {"latitude": None, "longitude": None},
            "weather_16_day_forecast": [],
            "air_quality": {"aqi": "N/A", "health_note": "Location or AQI service unavailable"},
            "traffic": {"status": "Unavailable"},
            "traveler_advice": "Live travel-intel services are unavailable. Check local conditions before travel.",
            "degraded": True,
        }
    import asyncio
    weather, aqi, traffic = await asyncio.gather(
        _safe_await(asyncio.to_thread(get_weather_16_days, lat, lon), []),
        _safe_await(asyncio.to_thread(get_aqi, city, lat, lon), {"aqi": "N/A", "health_note": "AQI unavailable"}),
        _safe_await(asyncio.to_thread(get_traffic_status, lat, lon), {"status": "Unavailable"}),
    )
    return {
        "city": city,
        "coordinates": {"latitude": lat, "longitude": lon},
        "weather_16_day_forecast": weather or [],
        "weather16DayForecast": weather or [],
        "air_quality": aqi or {"aqi": "N/A", "health_note": "AQI unavailable"},
        "airQuality": aqi or {"aqi": "N/A", "health_note": "AQI unavailable"},
        "traffic": traffic or {"status": "Unavailable"},
        "traveler_advice": build_traveler_advice(traffic or {"status": "Unavailable"}),
        "travelerAdvice": build_traveler_advice(traffic or {"status": "Unavailable"}),
        "degraded": not bool(weather or aqi or traffic),
    }

# ---------- image proxy ----------
@app.get("/img")
async def proxy_image(url: str):
    from urllib.parse import unquote
    decoded = unquote(url)
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(decoded)
            r.raise_for_status()
            return Response(content=r.content, media_type=r.headers.get("content-type", "image/jpeg"),
                            headers={"Cache-Control": "public, max-age=86400"})
    except Exception:
        raise HTTPException(status_code=404, detail="Image unavailable")

# ---------- WordPress travel memory proxy ----------
@app.post("/travel-memory")
async def travel_memory_proxy(
    title: str = Form(...), location: str = Form(...),
    latitude: float = Form(...), longitude: float = Form(...),
    date: str = Form(""), description: str = Form(""),
    photo: Optional[UploadFile] = File(None),
):
    wordpress_base = os.getenv("VOYAYAHA_WORDPRESS_URL", "https://voyayaha.com").rstrip("/")
    endpoint = f"{wordpress_base}/wp-json/voyayaha/v1/travel-memory"
    data = {"title": title, "location": location, "latitude": str(latitude), "longitude": str(longitude), "date": date, "description": description}
    files = None
    if photo:
        contents = await photo.read()
        if len(contents) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Photo is larger than 5 MB.")
        files = {"photo": (photo.filename or "travel-memory.jpg", contents, photo.content_type or "application/octet-stream")}
    try:
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.post(endpoint, data=data, files=files)
        try:
            payload = response.json()
        except Exception:
            payload = {"message": response.text}
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=payload)
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        print("WordPress proxy error:", repr(exc))
        raise HTTPException(status_code=502, detail="WordPress Travel Memory API could not be reached from Render.")
