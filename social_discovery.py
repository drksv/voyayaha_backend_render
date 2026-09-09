"""Verified social discovery for Voyayaha.

Searches Reddit and YouTube for a destination, extracts candidate place names
with the LLM, geocodes candidates, removes anything outside the requested
radius, and ranks the strongest three. If a provider/key fails, the other
provider and the local fallback can still be used.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
from typing import Any
from urllib.parse import quote_plus

import httpx
import praw
from dotenv import load_dotenv

from llm import generate_itinerary
from weather_openmeteo import get_lat_lon_from_city

load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT") or "voyayaha/1.0"
API_BASE = os.getenv("API_BASE", "https://backend-eqzz.onrender.com").rstrip("/")

_reddit = None
if all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT]):
    try:
        _reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
        )
    except Exception as exc:
        print("Reddit initialization error:", repr(exc))


def _proxify(url: str | None):
    return f"{API_BASE}/img?url={quote_plus(url)}" if url else None


async def _reddit_search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    if not _reddit:
        return []

    def run():
        rows = []
        # all is more useful than only r/travel for regional Indian discovery.
        for post in _reddit.subreddit("all").search(query, limit=limit, sort="relevance", time_filter="year"):
            title = getattr(post, "title", "") or ""
            text = getattr(post, "selftext", "") or ""
            image = None
            try:
                images = post.preview.get("images", [])
                if images:
                    image = images[0].get("source", {}).get("url")
            except Exception:
                pass
            thumb = getattr(post, "thumbnail", "") or ""
            if not image and thumb.startswith("http"):
                image = thumb
            rows.append({
                "source": "reddit",
                "title": title,
                "description": text[:500] or f"From r/{getattr(post, 'subreddit', 'travel')}",
                "image": _proxify(image),
                "url": f"https://www.reddit.com{getattr(post, 'permalink', '')}",
                "subreddit": str(getattr(post, "subreddit", "")),
            })
        return rows

    try:
        return await asyncio.to_thread(run)
    except Exception as exc:
        print("Reddit discovery error:", repr(exc))
        return []


async def _youtube_search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    if not YOUTUBE_API_KEY:
        return []
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "type": "video",
        "maxResults": min(max(limit, 1), 25),
        "q": query,
        "key": YOUTUBE_API_KEY,
        "relevanceLanguage": "en",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        rows = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            thumb = snippet.get("thumbnails", {}).get("medium", {}).get("url")
            rows.append({
                "source": "youtube",
                "title": snippet.get("title", "YouTube travel video"),
                "description": str(snippet.get("description", ""))[:500],
                "image": _proxify(thumb),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            })
        return rows
    except Exception as exc:
        print("YouTube discovery error:", repr(exc))
        return []


def _distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _extract_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return []
    try:
        return json.loads(value)
    except Exception:
        pass
    for left, right in [("[", "]"), ("{", "}")]:
        a, b = value.find(left), value.rfind(right)
        if a >= 0 and b > a:
            try:
                return json.loads(value[a:b + 1])
            except Exception:
                pass
    return []


async def _ai_candidates(location: str, interest: str, sources: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    if not sources:
        return []
    compact = [
        {"source": x["source"], "title": x.get("title", ""), "description": x.get("description", ""), "url": x.get("url", "")}
        for x in sources[:30]
    ]
    prompt = f"""
You are Voyayaha's social travel research analyst.
Main city: {location}
User interest: {interest or 'hidden and offbeat places'}

Below are real Reddit and YouTube search results. Extract only place names that
are actually mentioned or clearly identifiable in the supplied source text.
Do not invent places. Prefer villages, viewpoints, trails, waterfalls, heritage
sites and local experiences rather than generic city attractions.

Return ONLY a JSON array of at most {limit} objects with:
name, reason, source_indexes
source_indexes must be an array of integer indexes referring to the supplied
results (0-based). A candidate must have at least one source index.

SOURCES:
{json.dumps(compact, ensure_ascii=False)}
"""
    try:
        raw = await asyncio.to_thread(generate_itinerary, prompt)
        parsed = _extract_json(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception as exc:
        print("Social AI extraction error:", repr(exc))
        return []


async def _geocode(name: str, city: str) -> tuple[float | None, float | None]:
    # Open-Meteo is used first for a fast, no-key lookup.
    try:
        lat, lon = await asyncio.to_thread(get_lat_lon_from_city, f"{name}, {city}")
        if lat is not None and lon is not None:
            return float(lat), float(lon)
    except Exception:
        pass

    # Nominatim fallback. Keep a descriptive User-Agent as required by the service.
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Voyayaha/1.0 travel discovery"}) as client:
            r = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": f"{name}, {city}", "format": "json", "limit": 1},
            )
            r.raise_for_status()
            rows = r.json()
            if rows:
                return float(rows[0]["lat"]), float(rows[0]["lon"])
    except Exception as exc:
        print("Candidate geocoding error:", name, repr(exc))
    return None, None


def _local_candidate_names(sources: list[dict[str, Any]], city: str) -> list[str]:
    """Conservative no-LLM fallback: only extract title phrases that look like named places."""
    names: list[str] = []
    city_l = city.lower()
    for item in sources:
        title = item.get("title", "")
        # Strip common social title prefixes and avoid returning the city itself.
        cleaned = re.sub(r"^(best|top|hidden|offbeat|places?|things to do|travel|visit)\b[:\- ]*", "", title, flags=re.I).strip()
        if 2 <= len(cleaned.split()) <= 8 and city_l not in cleaned.lower():
            names.append(cleaned)
    return list(dict.fromkeys(names))[:12]


async def discover_social_places(location: str, query: str = "", radius_km: float = 100, limit: int = 3) -> dict[str, Any]:
    radius_km = min(max(float(radius_km or 100), 1), 250)
    limit = min(max(int(limit or 3), 1), 3)
    interest = query.strip() or "hidden offbeat places"

    center_lat, center_lon = await asyncio.to_thread(get_lat_lon_from_city, location)
    if center_lat is None or center_lon is None:
        return {"location": location, "radius_km": radius_km, "results": [], "degraded": True, "message": "Could not locate the main city."}

    searches = [
        f"{interest} near {location}",
        f"{interest} {location} travel",
        f"{interest} {location} weekend",
    ]
    reddit_results, youtube_results = await asyncio.gather(
        _reddit_search(searches[0], 10),
        _youtube_search(searches[0], 10),
    )
    # Add a second targeted search only when the first result set is sparse.
    if len(reddit_results) < 5:
        reddit_results += await _reddit_search(searches[1], 8)
    if len(youtube_results) < 5:
        youtube_results += await _youtube_search(searches[1], 8)

    # De-duplicate source records.
    sources: list[dict[str, Any]] = []
    seen = set()
    for row in reddit_results + youtube_results:
        key = row.get("url") or row.get("title")
        if key and key not in seen:
            seen.add(key)
            sources.append(row)

    candidates = await _ai_candidates(location, interest, sources, 12)
    if not candidates:
        candidates = [{"name": n, "reason": "Found in social travel search results.", "source_indexes": []} for n in _local_candidate_names(sources, location)]

    results: list[dict[str, Any]] = []
    for candidate in candidates[:12]:
        name = str(candidate.get("name", "")).strip()
        if not name or len(name) < 3:
            continue
        lat, lon = await _geocode(name, location)
        if lat is None or lon is None:
            continue
        distance = _distance_km(float(center_lat), float(center_lon), lat, lon)
        if distance > radius_km:
            continue

        idxs = candidate.get("source_indexes", [])
        matched = []
        if isinstance(idxs, list):
            for idx in idxs:
                if isinstance(idx, int) and 0 <= idx < len(sources):
                    matched.append(sources[idx])
        if not matched:
            name_terms = [t for t in re.findall(r"[a-z0-9]+", name.lower()) if len(t) > 2]
            matched = [s for s in sources if sum(t in (s.get("title", "") + " " + s.get("description", "")).lower() for t in name_terms) >= max(1, min(2, len(name_terms)))]

        reddit = [s for s in matched if s.get("source") == "reddit"][:3]
        youtube = [s for s in matched if s.get("source") == "youtube"][:3]
        score = 45.0
        score += min(25.0, len(reddit) * 10.0)
        score += min(20.0, len(youtube) * 8.0)
        score += max(0.0, 10.0 * (1.0 - distance / radius_km))
        results.append({
            "name": name,
            "latitude": lat,
            "longitude": lon,
            "distance_km": round(distance, 1),
            "score": round(score, 1),
            "reason": str(candidate.get("reason") or "Recommended from traveller discussions and videos."),
            "reddit": reddit,
            "youtube": youtube,
            "sources": matched[:6],
        })

    # De-duplicate by approximate coordinates/name and rank.
    unique: dict[str, dict[str, Any]] = {}
    for row in results:
        key = re.sub(r"[^a-z0-9]", "", row["name"].lower())
        if key not in unique or row["score"] > unique[key]["score"]:
            unique[key] = row
    ranked = sorted(unique.values(), key=lambda x: (-x["score"], x["distance_km"]))[:limit]
    for i, row in enumerate(ranked, 1):
        row["rank"] = i

    return {
        "location": location,
        "center": {"latitude": float(center_lat), "longitude": float(center_lon)},
        "radius_km": radius_km,
        "results": ranked,
        "sources_checked": {"reddit": len(reddit_results), "youtube": len(youtube_results)},
        "degraded": not bool(reddit_results or youtube_results),
    }
