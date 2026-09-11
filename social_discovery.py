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


def _configuration_status() -> dict[str, bool]:
    return {
        "youtube_api": bool(YOUTUBE_API_KEY),
        "reddit_api": bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET),
        "groq": bool(os.getenv("VY_GROQ_API_KEY") or os.getenv("GROQ_API_KEY")),
    }

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
    """Geocode a candidate and prefer results actually near the requested city.

    Landmark names are often ambiguous (for example "Waterfall" or "Fort"), so
    never accept the first India-wide hit blindly. We score returned results by
    city-name match and distance from the city centre.
    """
    queries = [
        f"{name}, {city}, Maharashtra, India" if city.lower() in {"mumbai", "pune", "thane", "nashik", "nagpur"} else f"{name}, {city}, India",
        f"{name}, {city}, India",
        f"{name}, {city}",
        f"{name}, India",
    ]

    city_lat, city_lon = await asyncio.to_thread(get_lat_lon_from_city, city)


    try:
        async with httpx.AsyncClient(timeout=10) as client:
            best: tuple[float, float, float] | None = None
            for q in queries:
                r = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": q, "count": 10, "language": "en", "format": "json"},
                )
                if not r.is_success:
                    continue
                for row in r.json().get("results", []):
                    lat, lon = row.get("latitude"), row.get("longitude")
                    if lat is None or lon is None:
                        continue
                    country = str(row.get("country_code", row.get("country", ""))).lower()
                    if country not in {"in", "india"} and "india" not in str(row).lower():
                        continue
                    d = _distance_km(city_lat, city_lon, float(lat), float(lon)) if city_lat is not None and city_lon is not None else 99999.0
                    text = str(row).lower()
                    city_match = 0 if city.lower() in text else 1
                    candidate = (city_match, d, float(lat), float(lon))
                    if best is None or candidate[:2] < best[:2]:
                        best = candidate
            if best is not None:
                # Do not accept an obviously unrelated India-wide result when a city
                # centre is known. The final radius check remains authoritative.
                if city_lat is None or city_lon is None or best[1] <= 250:
                    return best[2], best[3]
    except Exception:
        pass

    try:
        async with httpx.AsyncClient(timeout=12, headers={"User-Agent": "Voyayaha/1.0 (travel discovery)"}) as client:
            best: tuple[float, float, float] | None = None
            for q in queries[:3]:
                r = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": q, "format": "json", "limit": 8, "countrycodes": "in"},
                )
                if not r.is_success:
                    continue
                for row in r.json():
                    try:
                        lat, lon = float(row["lat"]), float(row["lon"])
                    except Exception:
                        continue
                    d = _distance_km(city_lat, city_lon, lat, lon) if city_lat is not None and city_lon is not None else 99999.0
                    text = str(row).lower()
                    city_match = 0 if city.lower() in text else 1
                    candidate = (city_match, d, lat, lon)
                    if best is None or candidate[:2] < best[:2]:
                        best = candidate
            if best is not None and (city_lat is None or city_lon is None or best[1] <= 250):
                return best[2], best[3]
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
identify actual places mentioned in the evidence, not the social posts themselves.
Do NOT invent destinations. Do NOT return a city name, subreddit, channel name,
year, generic phrase such as "top places", or the title of a video as a place.
Merge spelling variants and aliases of the same place into one candidate.
Prefer specific landmarks, villages, beaches, waterfalls, trails, temples,
viewpoints or neighbourhoods that match the user's intent.
A candidate is valid only when the supplied title/description/comment text gives
reasonable evidence that the place itself is being discussed.

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


def _fallback_candidates(sources: list[dict[str, Any]], city: str = "") -> list[dict[str, Any]]:
    """Extract conservative place-name candidates when the LLM is unavailable.

    This intentionally works from source text only. It does not invent places.
    """
    stop = {
        "top", "best", "hidden", "peaceful", "places", "place", "visit",
        "travel", "guide", "india", "mumbai", "pune", "thane", "weekend",
        "nature", "secret", "beautiful", "tourist", "tourism", "video",
        "shorts", "official", "2026", "2025", "2024", "near", "and", "the",
    }
    candidates: dict[str, dict[str, Any]] = {}
    for idx, item in enumerate(sources):
        text = " ".join([
            str(item.get("title", "")),
            str(item.get("description", "")),
            " ".join(item.get("comments", [])[:5]) if isinstance(item.get("comments"), list) else "",
        ])
        # Capitalized multi-word names, e.g. "Marine Drive", "Colaba Causeway".
        phrases = re.findall(r"\b[A-Z][A-Za-z'&.-]*(?:\s+[A-Z][A-Za-z'&.-]*){0,3}\b", text)
        for phrase in phrases:
            name = re.sub(r"\s+", " ", phrase).strip(" .,:;|-/")
            words = name.split()
            if not 1 <= len(words) <= 4:
                continue
            if all(w.lower().strip(".,") in stop for w in words):
                continue
            if name.lower() in {city.lower(), "reddit", "youtube"}:
                continue
            key = re.sub(r"[^a-z0-9]", "", name.lower())
            if len(key) < 4:
                continue
            row = candidates.setdefault(key, {
                "name": name, "source_indexes": [], "evidence": "", "themes": [], "confidence": 0.35
            })
            if idx not in row["source_indexes"]:
                row["source_indexes"].append(idx)
    rows = list(candidates.values())
    rows.sort(key=lambda x: len(x["source_indexes"]), reverse=True)
    for row in rows:
        row["evidence"] = f"Mentioned in {len(row['source_indexes'])} traveller source(s)."
    return rows[:15]


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
                    {"source": x.get("source"), "title": x.get("title"), "description": x.get("description", "")[:700], "comments": x.get("comments", [])[:3]}
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
        f"hidden offbeat places {location}",
        f"peaceful places {location}",
        f"lesser known places {location}",
    ]
    # More search variants improve place recall. We keep the final UI limited to
    # exactly three verified places, but the research stage can inspect many sources.
    reddit_tasks = [_reddit_search(q, 10, "relevance") for q in searches[:4]]
    youtube_tasks = [
        _youtube_search(searches[0], 10, "relevance"),
        _youtube_search(searches[1], 10, "date"),
        _youtube_search(searches[2], 10, "viewCount"),
        _youtube_search(searches[3], 10, "relevance"),
        _youtube_search(searches[4], 10, "date"),
        _youtube_search(searches[5], 10, "viewCount"),
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
    # Keep the LLM extraction as the preferred source, but supplement it with
    # conservative source-text extraction when it found too few candidates.
    # This prevents a single weak LLM response from turning a rich social search
    # into one or zero recommendations.
    fallback_candidates = _fallback_candidates(sources, location)
    if len(candidates) < 8:
        existing = {re.sub(r"[^a-z0-9]", "", str(x.get("name", "")).lower()) for x in candidates if isinstance(x, dict)}
        for extra in fallback_candidates:
            key = re.sub(r"[^a-z0-9]", "", str(extra.get("name", "")).lower())
            if key and key not in existing:
                candidates.append(extra)
                existing.add(key)
            if len(candidates) >= 15:
                break

    # Some LLM responses omit source_indexes. Recover them deterministically by
    # matching the candidate name against the actual source text. This prevents a
    # valid place from being discarded merely because the model omitted metadata.
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        idxs = candidate.get("source_indexes")
        if not isinstance(idxs, list) or not idxs:
            name = _clean_text(candidate.get("name", ""), 180).lower()
            if name:
                tokens = [t for t in re.findall(r"[a-z0-9]+", name) if len(t) >= 3]
                matches = []
                for si, src in enumerate(sources):
                    text = " ".join([str(src.get("title", "")), str(src.get("description", "")), " ".join(src.get("comments", []) if isinstance(src.get("comments"), list) else [])]).lower()
                    if name in text or (tokens and sum(t in text for t in tokens) >= max(1, len(tokens) - 1)):
                        matches.append(si)
                candidate["source_indexes"] = matches[:10]

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
    ranked_candidates = sorted(unique.values(), key=lambda x: (-x["social_score"], x["distance_km"]))[:15]

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
            "score": base["social_score"],
            "reason": _clean_text(item.get("why_selected", ""), 500) or base["evidence"],
            "summary": _clean_text(item.get("summary", ""), 900) or base["evidence"],
            "why_selected": _clean_text(item.get("why_selected", ""), 500),
            "traveller_signals": item.get("traveller_signals", []) if isinstance(item.get("traveller_signals"), list) else [],
            "best_for": _clean_text(item.get("best_for", ""), 160),
            "caveat": _clean_text(item.get("caveat", ""), 300),
            "ai_confidence": float(item.get("confidence", base["confidence"]) or base["confidence"]),
        })

    # If the LLM returns fewer than three selections, fill the remaining slots
    # from the already-ranked, geographically verified candidates. The final UI
    # can therefore consistently show three places whenever three candidates
    # were successfully verified.
    if len(final) < limit:
        for base in ranked_candidates:
            if len(final) >= limit:
                break
            key = re.sub(r"[^a-z0-9]", "", base["name"].lower())
            if key in used:
                continue
            used.add(key)
            final.append({
                **base,
                "rank": len(final) + 1,
                "score": base["social_score"],
                "reason": "Strong social evidence and verified distance within the requested radius.",
                "summary": base["evidence"] or "Found in traveller social sources.",
                "why_selected": "Strong social evidence and verified distance within the requested radius.",
                "traveller_signals": [],
                "best_for": interest,
                "caveat": "This place was ranked from the verified social evidence; AI synthesis was not available for this card.",
                "ai_confidence": base["confidence"],
            })

    # If Groq is unavailable, the deterministic cards above still remain useful
    # and transparent. They are never presented as an AI summary unless one was
    # actually generated.
    if not final:
        for base in ranked_candidates[:limit]:
            final.append({
                **base,
                "rank": len(final) + 1,
                "score": base["social_score"],
                "reason": "Strong social evidence and verified distance within the requested radius.",
                "summary": base["evidence"] or "Found in traveller social sources.",
                "why_selected": "Strongest available social and geographic evidence.",
                "traveller_signals": [],
                "best_for": interest,
                "caveat": "AI summary unavailable; source evidence is shown below.",
                "ai_confidence": base["confidence"],
            })

    sources_checked = {"reddit": sum(len(x) for x in reddit_sets), "youtube": sum(len(x) for x in youtube_sets)}
    config = _configuration_status()
    diagnostics = {
        "configuration": config,
        "sources_collected": len(sources),
        "candidates_extracted": len(candidates),
        "geographically_verified": len(ranked_candidates),
    }
    if not sources:
        message = "No Reddit or YouTube evidence was collected. On Render, add YOUTUBE_API_KEY and REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET."
    elif len(ranked_candidates) < limit:
        message = f"Only {len(ranked_candidates)} social places could be geographically verified within {radius_km:g} km of {location}."
    else:
        message = "Social recommendations verified."

    return {
        "location": location,
        "center": {"latitude": float(center_lat), "longitude": float(center_lon)},
        "radius_km": radius_km,
        "results": final[:limit],
        "sources_checked": sources_checked,
        "candidates_checked": len(ranked_candidates),
        "diagnostics": diagnostics,
        "message": message,
        "method": "Reddit + YouTube discovery → AI place extraction → geocoding → 100 km verification → social/recency ranking → AI synthesis",
        "degraded": not bool(sources),
    }
