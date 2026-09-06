"""Non-destructive AI helper for Voyayaha Hidden Places / peaceful-place search.
Does not modify or replace the existing llm.py module.
"""
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("VY_GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.getenv("VY_HIDDEN_GROQ_MODEL", "llama-3.1-8b-instant")


def _extract_array(text: str):
    try:
        value = json.loads(text)
        if isinstance(value, list):
            return value
    except Exception:
        pass
    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        try:
            value = json.loads(text[start:end])
            if isinstance(value, list):
                return value
        except Exception:
            pass
    return []


def generate_hidden_itinerary(location: str, query: str = "", limit: int = 3):
    """Return exactly up to three place recommendations without touching llm.py."""
    limit = max(1, min(int(limit or 3), 3))
    focus = query.strip() or "hidden and peaceful places"
    prompt = f"""
You are Voyayaha's local travel discovery guide.

Destination: {location}
User search: {focus}

Recommend exactly {limit} REAL places in or very near {location} that match the search.
Prioritize lesser-known, peaceful, scenic, cultural, nature, heritage, or local places when appropriate.
Do not invent places. If a famous place is the best fit, it may be included.
Return ONLY a valid JSON array. Each object must contain:
- name: place name
- description: 1-2 concise sentences
- tip: one practical local tip
- category: short category

Do not include markdown, URLs, or commentary outside the JSON array.
"""

    if not GROQ_API_KEY:
        return []

    try:
        response = requests.post(
            GROQ_URL,
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": "Return only valid JSON arrays."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 900,
            },
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        results = _extract_array(content)
        cleaned = []
        for item in results:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            cleaned.append({
                "name": str(item.get("name", "")).strip(),
                "description": str(item.get("description", "")).strip(),
                "tip": str(item.get("tip", "")).strip(),
                "category": str(item.get("category", "Hidden place")).strip(),
            })
        return cleaned[:limit]
    except Exception as exc:
        print("ERROR in generate_hidden_itinerary:", exc)
        return []
