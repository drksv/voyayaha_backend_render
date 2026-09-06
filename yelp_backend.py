import os
import aiohttp

YELP_API_KEY = os.getenv("YELP_API_KEY")


async def search_yelp(location: str, query: str):
    if not YELP_API_KEY:
        return []

    url = "https://api.yelp.com/v3/businesses/search"
    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    params = {"location": location, "term": query, "limit": 10, "sort_by": "rating"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as res:
            try:
                data = await res.json()
                businesses = data.get("businesses", [])
                return [
                    {
                        "name": b["name"],
                        "rating": b.get("rating", "n/a"),
                        "address": ", ".join(b["location"].get("display_address", [])),
                        "image": b.get("image_url"),
                        "url": b.get("url"),
                        "lat": b["coordinates"].get("latitude"),
                        "lon": b["coordinates"].get("longitude"),
                    }
                    for b in businesses
                ]
            except:
                return []
