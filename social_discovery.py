from __future__ import annotations

import asyncio
import json
import math
import os
import re
from datetime import datetime, timezone
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
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "voyayaha/1.0")
API_BASE = os.getenv("API_BASE", "https://backend-eqzz.onrender.com").rstrip("/")

reddit = None
if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
    try:
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            check_for_async=False,
        )
    except Exception as exc:
        print("Reddit client setup error:", repr(exc))
        reddit = None


def _proxify(url: str | None) -> str | None:
    if not url:
        return None
    return f"{API_BASE}/img?url={quote_plus(url)}"


def _clean_text(value: Any, limit: int = 1000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


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
    for left, right in (("[", "]"), ("{", "}")):
        a, b = value.find(left), value.rfind(right)
        if a >= 0 and b > a:
            try:
                return json.loads(value[a : b + 1])
            except Exception:
                pass
    return []


async def _reddit_search(query: str, limit: int = 12, sort: str = "relevance") -> list[dict[str, Any]]:
    if reddit is None:
        return []

    def run() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            # Search across Reddit, not just r/travel. This is important for
            # regional Indian travel questions where local subreddits are more useful.
            for post in reddit.subreddit("all").search(query, limit=limit, sort=sort, time_filter="year"):
                body = _clean_text(getattr(post, "selftext", ""), 1400)
                comments: list[str] = []
                try:
                    post.comment_sort = "top"
                    post.comments.replace_more(limit=0)
                    for comment in list(post.comments)[:5]:
                        text = _clean_text(getattr(comment, "body", ""), 500)
                        if text:
                            comments.append(text)
                except Exception:
                    pass

                image = None
                try:
                    preview = getattr(post, "preview", {}) or {}
                    images = preview.get("images", [])
                    if images:
                        image = images[0].get("source", {}).get("url")
                except Exception:
                    pass
                if not image:
                    thumb = str(getattr(post, "thumbnail", "") or "")
                    if thumb.startswith("http"):
                        image = thumb

                created = getattr(post, "created_utc", None)
                age_days = 365.0
                if created:
                    age_days = max(0.0, (datetime.now(timezone.utc).timestamp() - float(created)) / 86400)

                rows.append(
                    {
                        "source": "reddit",
                        "title": _clean_text(getattr(post, "title", "Reddit travel discussion"), 300),
                        "description": body or _clean_text(comments[0] if comments else "Traveller discussion", 500),
                        "comments": comments,
                        "image": _proxify(image),
                        "url": f"https://www.reddit.com{getattr(post, 'permalink', '')}",
                        "subreddit": str(getattr(post, "subreddit", "")),
                        "score": int(getattr(post, "score", 0) or 0),
                        "comment_count": int(getattr(post, "num_comments", 0) or 0),
                        "age_days": round(age_days, 1),
                    }
                )
        except Exception as exc:
            print("Reddit discovery error:", repr(exc))
        return rows

    return await asyncio.to_thread(run)


async def _youtube_search(query: str, limit: int = 10, order: str = "relevance") -> list[dict[str, Any]]:
    if not YOUTUBE_API_KEY:
        return []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            search_response = await client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "type": "video",
                    "maxResults": min(max(limit, 1), 25),
                    "q": query,
                    "key": YOUTUBE_API_KEY,
                    "relevanceLanguage": "en",
                    "order": order,
                },
            )
            search_response.raise_for_status()
            search_data = search_response.json()

            ids = [x.get("id", {}).get("videoId") for x in search_data.get("items", [])]
            ids = [x for x in ids if x]
            stats: dict[str, dict[str, Any]] = {}
            if ids:
                details = await client.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={"part": "statistics,contentDetails,snippet", "id": ",".join(ids), "key": YOUTUBE_API_KEY},
                )
                if details.is_success:
                    for item in details.json().get("items", []):
                        stats[item["id"]] = item

        rows: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).timestamp()
        for item in search_data.get("items", []):
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            detail = stats.get(video_id, {})
            statistics = detail.get("statistics", {})
            published = snippet.get("publishedAt")
            age_days = 365.0
            if published:
                try:
                    age_days = max(0.0, (now - datetime.fromisoformat(published.replace("Z", "+00:00")).timestamp()) / 86400)
                except Exception:
                    pass
            views = int(statistics.get("viewCount", 0) or 0)
            likes = int(statistics.get("likeCount", 0) or 0)
            comments = int(statistics.get("commentCount", 0) or 0)
            rows.append(
                {
                    "source": "youtube",
                    "title": _clean_text(snippet.get("title", "YouTube travel video"), 300),
                    "description": _clean_text(snippet.get("description", ""), 1200),
                    "image": _proxify((snippet.get("thumbnails", {}).get("medium") or {}).get("url")),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "channel": _clean_text(snippet.get("channelTitle", ""), 150),
                    "published_at": published,
                    "age_days": round(age_days, 1),
                    "views": views,
                    "likes": likes,
                    "comment_count": comments,
                }
            )
        return rows
    except Exception as exc:
        print("YouTube discovery error:", repr(exc))
        return []


async def _geocode(name: str, city: str) -> tuple[float | None, float | None]:
    # Open-Meteo first, Nominatim second. Neither requires another paid API key.
    try:
        lat, lon = await asyncio.to_thread(get_lat_lon_from_city, f"{name}, {city}")
        if lat is not None and lon is not None:
            return float(lat), float(lon)
    except Exception:
        pass

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


async def _extract_candidates(city: str, interest: str, sources: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    if not sources:
        return []

    compact = []
    for i, item in enumerate(sources[:50]):
        compact.append(
            {
                "index": i,
                "source": item.get("source"),
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "comments": item.get("comments", [])[:3],
                "channel": item.get("channel", ""),
                "subreddit": item.get("subreddit", ""),
                "views": item.get("views", 0),
                "score": item.get("score", 0),
                "url": item.get("url", ""),
            }
        )

    prompt = f"""
You are Voyayaha's travel research analyst.
Main city: {city}
User request: {interest}

Analyze the supplied REAL Reddit and YouTube search evidence. Your job is to
identify actual places mentioned in that evidence. Do NOT invent destinations.
Merge spelling variants and aliases of the same place into one candidate.
Prefer places that match the user's intent (especially hidden/offbeat/village
requests) over generic famous attractions.

Return ONLY JSON with this schema:
[
  {{
    "name": "actual place name",
    "source_indexes": [0, 4],
    "evidence": "short factual explanation of what the supplied sources say",
    "themes": ["quiet", "nature"],
    "confidence": 0.0
  }}
]
Return up to {limit} candidates. Every candidate MUST have at least one valid
source index. Never create a candidate merely because you know it from memory.

SOURCE MATERIAL:
{json.dumps(compact, ensure_ascii=False)}
"""

    try:
        raw = await asyncio.to_thread(generate_itinerary, prompt)
        parsed = _extract_json(raw)
        if not isinstance(parsed, list):
            return []
        return [x for x in parsed if isinstance(x, dict)][:limit]
    except Exception as exc:
        print("Social candidate extraction error:", repr(exc))
        return []


def _fallback_candidates(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # No-LLM fallback. It is deliberately conservative: it uses only likely
    # proper-name phrases from source titles and never pretends certainty.
    names: list[str] = []
    for item in sources:
        title = _clean_text(item.get("title", ""), 250)
        cleaned = re.sub(
            r"^(best|top|hidden|offbeat|places?|things to do|travel|visit|guide)\b[:\- ]*",
            "",
            title,
            flags=re.I,
        ).strip()
        if 2 <= len(cleaned.split()) <= 8:
            names.append(cleaned)
    return [{"name": n, "source_indexes": [], "evidence": "Found in social travel search results.", "themes": [], "confidence": 0.35} for n in list(dict.fromkeys(names))[:12]]


async def _synthesize_ranked_places(
    city: str,
    interest: str,
    candidates: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    radius_km: float,
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    evidence = []
    for i, c in enumerate(candidates):
        idxs = c.get("source_indexes", []) if isinstance(c.get("source_indexes"), list) else []
        matched = [sources[j] for j in idxs if isinstance(j, int) and 0 <= j < len(sources)]
        evidence.append(
            {
                "candidate": i,
                "name": c.get("name", ""),
                "distance_km": c.get("distance_km"),
                "social_score": c.get("social_score", 0),
                "reddit_mentions": c.get("reddit_mentions", 0),
                "youtube_mentions": c.get("youtube_mentions", 0),
                "themes": c.get("themes", []),
                "evidence": c.get("evidence", ""),
                "sources": [
                    {"source": x.get("source"), "title": x.get("title"), "description": x.get("description", "")[:500]}
                    for x in matched[:8]
                ],
            }
        )

    prompt = f"""
You are Voyayaha's final travel recommendation editor.
City: {city}
User request: {interest}
Maximum radius: {radius_km} km

These candidates have ALREADY been geographically checked. Rank the best 3
based only on the supplied evidence. Favor genuine traveller interest,
recency/trending momentum, relevance to the request, and cross-source support.
Do not invent facts not present in the evidence.

For each selected place return:
- name
- summary: 2-3 sentences synthesizing the social evidence
- why_selected: 1-2 sentences
- traveller_signals: 3 short bullet-like strings
- best_for: short phrase
- caveat: short phrase, or empty string
- confidence: 0 to 1

Return ONLY JSON array, maximum 3 items, in ranking order. The candidate
number must be preserved as candidate_index.

CANDIDATES:
{json.dumps(evidence, ensure_ascii=False)}
"""
    try:
        raw = await asyncio.to_thread(generate_itinerary, prompt)
        parsed = _extract_json(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception as exc:
        print("Social synthesis error:", repr(exc))
        return []


async def discover_social_places(location: str, query: str = "", radius_km: float = 100, limit: int = 3) -> dict[str, Any]:
    radius_km = min(max(float(radius_km or 100), 1), 250)
    limit = min(max(int(limit or 3), 1), 3)
    interest = query.strip() or "hidden offbeat places"

    center_lat, center_lon = await asyncio.to_thread(get_lat_lon_from_city, location)
    if center_lat is None or center_lon is None:
        return {
            "location": location,
            "radius_km": radius_km,
            "results": [],
            "degraded": True,
            "message": "Could not locate the main city.",
        }

    # Several searches improve recall. The second YouTube search uses recent
    # uploads and the third uses popularity, giving us a lightweight trending signal.
    searches = [
        f"{interest} near {location}",
        f"{interest} {location} travel",
        f"{interest} {location} weekend",
    ]
    reddit_tasks = [_reddit_search(q, 10, "relevance") for q in searches[:2]]
    youtube_tasks = [
        _youtube_search(searches[0], 10, "relevance"),
        _youtube_search(searches[1], 8, "date"),
        _youtube_search(searches[2], 8, "viewCount"),
    ]
    reddit_sets, youtube_sets = await asyncio.gather(asyncio.gather(*reddit_tasks), asyncio.gather(*youtube_tasks))

    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in list(reddit_sets) + list(youtube_sets):
        for row in group:
            key = row.get("url") or row.get("title")
            if key and key not in seen:
                seen.add(key)
                sources.append(row)

    candidates = await _extract_candidates(location, interest, sources, 15)
    if not candidates:
        candidates = _fallback_candidates(sources)

    prepared: list[dict[str, Any]] = []
    sem = asyncio.Semaphore(3)

    async def prepare(candidate: dict[str, Any]) -> dict[str, Any] | None:
        name = _clean_text(candidate.get("name", ""), 180)
        if len(name) < 3:
            return None
        async with sem:
            lat, lon = await _geocode(name, location)
        if lat is None or lon is None:
            return None
        distance = _distance_km(float(center_lat), float(center_lon), lat, lon)
        if distance > radius_km:
            return None

        idxs = candidate.get("source_indexes", []) if isinstance(candidate.get("source_indexes"), list) else []
        matched = [sources[j] for j in idxs if isinstance(j, int) and 0 <= j < len(sources)]
        if not matched:
            terms = [x for x in re.findall(r"[a-z0-9]+", name.lower()) if len(x) > 2]
            matched = [
                s for s in sources
                if terms and sum(t in (s.get("title", "") + " " + s.get("description", "")).lower() for t in terms) >= max(1, min(2, len(terms)))
            ]

        reddit_rows = [s for s in matched if s.get("source") == "reddit"]
        youtube_rows = [s for s in matched if s.get("source") == "youtube"]
        recency = 0.0
        engagement = 0.0
        for s in matched:
            age = float(s.get("age_days", 365) or 365)
            recency += max(0.0, 1.0 - age / 365.0)
            engagement += math.log1p(float(s.get("views", 0) or 0)) / 10 if s.get("source") == "youtube" else math.log1p(float(s.get("score", 0) or 0) + float(s.get("comment_count", 0) or 0))
        confidence = float(candidate.get("confidence", 0.5) or 0.5)
        # Ranking is deterministic and independent of the LLM's final prose.
        social_score = (
            min(25.0, len(reddit_rows) * 7.0)
            + min(25.0, len(youtube_rows) * 6.0)
            + min(15.0, recency * 2.0)
            + min(15.0, engagement)
            + min(10.0, len({s.get("source") for s in matched}) * 5.0)
            + min(10.0, max(0.0, 10.0 * (1.0 - distance / radius_km)))
        )
        return {
            "name": name,
            "latitude": lat,
            "longitude": lon,
            "distance_km": round(distance, 1),
            "social_score": round(social_score, 1),
            "reddit_mentions": len(reddit_rows),
            "youtube_mentions": len(youtube_rows),
            "reddit": reddit_rows[:5],
            "youtube": youtube_rows[:5],
            "sources": matched[:10],
            "evidence": _clean_text(candidate.get("evidence", ""), 700),
            "themes": candidate.get("themes", []) if isinstance(candidate.get("themes"), list) else [],
            "confidence": confidence,
        }

    prepared = [x for x in await asyncio.gather(*(prepare(c) for c in candidates[:15])) if x]

    # De-duplicate names and keep strongest evidence for each place.
    unique: dict[str, dict[str, Any]] = {}
    for row in prepared:
        key = re.sub(r"[^a-z0-9]", "", row["name"].lower())
        if key not in unique or row["social_score"] > unique[key]["social_score"]:
            unique[key] = row
    ranked_candidates = sorted(unique.values(), key=lambda x: (-x["social_score"], x["distance_km"]))[:8]

    synthesis = await _synthesize_ranked_places(location, interest, ranked_candidates, sources, radius_km)
    by_index = {i: c for i, c in enumerate(ranked_candidates)}
    final: list[dict[str, Any]] = []
    used: set[str] = set()
    for item in synthesis[:limit]:
        if not isinstance(item, dict):
            continue
        idx = item.get("candidate_index")
        base = by_index.get(idx) if isinstance(idx, int) else None
        if base is None:
            # Match by name if the model omitted candidate_index.
            target = re.sub(r"[^a-z0-9]", "", str(item.get("name", "")).lower())
            base = next((c for c in ranked_candidates if re.sub(r"[^a-z0-9]", "", c["name"].lower()) == target), None)
        if base is None:
            continue
        key = re.sub(r"[^a-z0-9]", "", base["name"].lower())
        if key in used:
            continue
        used.add(key)
        final.append({
            **base,
            "rank": len(final) + 1,
            "summary": _clean_text(item.get("summary", ""), 900) or base["evidence"],
            "why_selected": _clean_text(item.get("why_selected", ""), 500),
            "traveller_signals": item.get("traveller_signals", []) if isinstance(item.get("traveller_signals"), list) else [],
            "best_for": _clean_text(item.get("best_for", ""), 160),
            "caveat": _clean_text(item.get("caveat", ""), 300),
            "ai_confidence": float(item.get("confidence", base["confidence"]) or base["confidence"]),
        })

    # If Groq is unavailable, still return the deterministic top candidates with
    # transparent wording. This keeps the feature useful without pretending AI synthesized it.
    if not final:
        for base in ranked_candidates[:limit]:
            final.append({
                **base,
                "rank": len(final) + 1,
                "summary": base["evidence"] or "Found in traveller social sources.",
                "why_selected": "Strongest available social and geographic evidence.",
                "traveller_signals": [],
                "best_for": interest,
                "caveat": "AI summary unavailable; source evidence is shown below.",
                "ai_confidence": base["confidence"],
            })

    return {
        "location": location,
        "center": {"latitude": float(center_lat), "longitude": float(center_lon)},
        "radius_km": radius_km,
        "results": final[:limit],
        "sources_checked": {"reddit": sum(len(x) for x in reddit_sets), "youtube": sum(len(x) for x in youtube_sets)},
        "candidates_checked": len(ranked_candidates),
        "method": "Reddit + YouTube discovery → AI place extraction → geocoding → 100 km verification → social/recency ranking → AI synthesis",
        "degraded": not bool(sources),
    }
