# foursquare_backend.py
import os
import httpx
from typing import List, Dict, Any

FOURSQUARE_API_KEY = os.getenv("FOURSQUARE_API_KEY")
FOURSQUARE_BASE = "https://api.foursquare.com/v3/places/search"

async def foursquare_search(location: str, query: str = "", limit: int = 6) -> List[Dict[str, Any]]:
    """
    Async Foursquare search. Returns normalized dicts.
    """
    if not FOURSQUARE_API_KEY:
        return []

    headers = {"Authorization": FOURSQUARE_API_KEY}
    params = {
        "query": query or "tourist",
        "near": location,
        "limit": limit
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(FOURSQUARE_BASE, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    out = []
    for item in data.get("results", []):
        out.append({
            "title": item.get("name"),
            "rating": item.get("rating", None),
            "categories": [c.get("name") for c in item.get("categories", [])],
            "address": ", ".join(item.get("location", {}).get("formatted_address", [])) if item.get("location") else "",
            "url": item.get("fsq_id"),
            "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a6/Blank_map.png/600px-Blank_map.png",
            "source": "foursquare"
        })
    return out
