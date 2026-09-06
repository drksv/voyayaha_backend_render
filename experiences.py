import aiohttp
import os
from yelp_backend import search_yelp
from weather import get_weather_and_risk as get_weather

GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")


async def search_geoapify(location: str, query: str):
    """
    Geoapify fallback search for POIs (FIXED)
    """
    if not GEOAPIFY_API_KEY:
        print("❌ GEOAPIFY_API_KEY not set")
        return []

    url = "https://api.geoapify.com/v2/places"

    # ✅ IMPORTANT: add filter to satisfy Geoapify requirements
    params = {
        "text": f"{query}",
        "filter": f"place:city:{location}",
        "limit": 12,
        "apiKey": GEOAPIFY_API_KEY,
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(url, params=params) as res:
                text = await res.text()

                if res.status != 200:
                    print("❌ Geoapify HTTP error:", res.status)
                    print("Geoapify response:", text)
                    return []

                data = await res.json()
                features = data.get("features", [])

                results = []
                for f in features:
                    props = f.get("properties", {})
                    coords = f.get("geometry", {}).get("coordinates", [None, None])

                    results.append({
                        "name": props.get("name", "Unknown place"),
                        "category": props.get("categories", []),
                        "address": props.get("formatted"),
                        "lat": coords[1],
                        "lon": coords[0],
                        "source": "geoapify"
                    })

                print(f"✅ Geoapify results: {len(results)}")
                return results

    except Exception as e:
        print("❌ Geoapify exception:", str(e))
        return []

async def get_combined_experiences(location: str, query: str):
    print(f"🔎 Searching experiences for: {location} | query: {query}")

    # 1. Weather
    try:
        weather = await get_weather(location)   # 🔑 FIXED NAME
        print("🌦 Weather:", weather)
    except Exception as e:
        print("❌ Weather error:", e)
        weather = {
            "summary": "Unknown",
            "temperature_c": "N/A",
            "indoor_preferred": True
        }

    indoor_only = weather.get("indoor_preferred", True)

    # Modify query based on weather
    if indoor_only:
        query = query + " indoor"
    else:
        query = query + " outdoor"

    # 2. Yelp
    try:
        yelp_results = await search_yelp(location, query)
        print(f"✅ Yelp results: {len(yelp_results)}")
    except Exception as e:
        print("❌ Yelp error:", e)
        yelp_results = []

    # 3. Geoapify
    geo_results = await search_geoapify(location, query)

    # 4. Fallback
    if not yelp_results and not geo_results:
        print("⚠️ Both empty, trying generic 'tourist attractions'")
        geo_results = await search_geoapify(location, "tourist attractions")

    return {
        "weather": weather,
        "indoor_only": indoor_only,
        "yelp": yelp_results,
        "geoapify": geo_results
    }

