"""AI ranking/synthesis for Voyayaha Hidden Places.

The LLM is used AFTER Reddit/YouTube discovery. It is instructed to select
only places supported by the supplied social evidence, reducing hallucinated
places while keeping the UI useful when a provider is unavailable.
"""
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("VY_GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.getenv("VY_HIDDEN_GROQ_MODEL") or os.getenv("VY_GROQ_MODEL") or "llama-3.1-8b-instant"


def _extract_json(text: str):
    try:
        value = json.loads(text)
        return value
    except Exception:
        pass
    for left, right in [("[", "]"), ("{", "}")]:
        start = text.find(left)
        end = text.rfind(right)
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                continue
    return []


def _clean(items, limit=3):
    out = []
    seen = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("title") or "").strip()
        key = " ".join(name.lower().split())
        if not name or key in seen:
            continue
        seen.add(key)
        out.append({
            "name": name,
            "description": str(item.get("description") or "").strip(),
            "tip": str(item.get("tip") or "").strip(),
            "category": str(item.get("category") or "Hidden place").strip(),
            "source": str(item.get("source") or "social").strip(),
            "source_url": str(item.get("source_url") or item.get("url") or "").strip(),
            "image": item.get("image"),
            "evidence": str(item.get("evidence") or "").strip(),
        })
        if len(out) >= limit:
            break
    return out


def rank_social_hidden_places(location: str, query: str, social_results: list, limit: int = 3):
    """Use Groq to turn Reddit/YouTube evidence into exactly up to 3 places."""
    limit = max(1, min(int(limit or 3), 3))
    if not social_results:
        return []
    if not GROQ_API_KEY:
        return []

    evidence = []
    for i, item in enumerate(social_results[:24], 1):
        evidence.append({
            "id": i,
            "source": item.get("source", "social"),
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "url": item.get("url", ""),
        })

    prompt = f"""
You are Voyayaha's AI hidden-place discovery editor.
Location: {location}
User query: {query or 'hidden, offbeat and peaceful places'}

Below is evidence retrieved LIVE from Reddit and YouTube. Select exactly {limit}
real places that are most useful to a traveler. Prefer places that are lesser-known,
local, scenic, cultural, village, nature or otherwise offbeat. Prioritize evidence
that appears repeatedly or is clearly about the requested location.

STRICT RULES:
1. You may ONLY recommend a place whose name is supported by the supplied evidence.
2. Do not invent a place, business, address, URL, review, popularity claim or fact.
3. A Reddit/YouTube title can support a place name, but describe uncertainty when evidence is weak.
4. Return ONLY JSON, no markdown.
5. Each result must contain: name, description, tip, category, source_ids.
6. source_ids must be an array of evidence ids used for that recommendation.

SOCIAL EVIDENCE:
{json.dumps(evidence, ensure_ascii=False)}
"""

    try:
        response = requests.post(
            GROQ_URL,
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": "Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 1400,
            },
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=35,
        )
        response.raise_for_status()
        raw = response.json().get("choices", [{}])[0].get("message", {}).get("content", "[]")
        ranked = _extract_json(raw)
        if isinstance(ranked, dict):
            ranked = ranked.get("places") or ranked.get("results") or []

        source_by_id = {i + 1: x for i, x in enumerate(social_results[:24])}
        final = []
        seen = set()
        for item in ranked if isinstance(ranked, list) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name or name.lower() in seen:
                continue
            ids = item.get("source_ids") or []
            if not isinstance(ids, list):
                ids = [ids]
            sources = [source_by_id.get(int(x)) for x in ids if str(x).isdigit() and int(x) in source_by_id]
            sources = [x for x in sources if x]
            if not sources:
                continue
            primary = sources[0]
            final.append({
                "name": name,
                "description": str(item.get("description") or primary.get("description") or "").strip(),
                "tip": str(item.get("tip") or "Check the linked community/video source before travelling.").strip(),
                "category": str(item.get("category") or "Hidden place").strip(),
                "source": ", ".join(sorted({str(x.get("source", "social")) for x in sources})),
                "source_url": primary.get("url"),
                "image": primary.get("image"),
                "evidence": "; ".join(str(x.get("title") or "")[:180] for x in sources[:2]),
            })
            seen.add(name.lower())
            if len(final) >= limit:
                break
        return final
    except Exception as exc:
        print("ERROR in rank_social_hidden_places:", repr(exc))
        return []


# Backward-compatible helper used by older routes.
def generate_hidden_itinerary(location: str, query: str = "", limit: int = 3):
    """AI-only fallback for older callers."""
    limit = max(1, min(int(limit or 3), 3))
    if not GROQ_API_KEY:
        return []
    prompt = f"""
Recommend up to {limit} real lesser-known places in or near {location} matching {query or 'hidden peaceful places'}.
Return ONLY JSON array with name, description, tip and category.
Do not invent places; if uncertain return fewer results.
"""
    try:
        response = requests.post(GROQ_URL, json={
            "model": MODEL,
            "messages": [{"role": "system", "content": "Return only valid JSON arrays."}, {"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 900,
        }, headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}, timeout=30)
        response.raise_for_status()
        return _clean(_extract_json(response.json()["choices"][0]["message"]["content"]), limit)
    except Exception as exc:
        print("ERROR in generate_hidden_itinerary:", repr(exc))
        return []
