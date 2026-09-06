import aiohttp
import os

GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")

GEOAPIFY_GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"


def label_from_category(categories):
    """
    Convert Geoapify categories to friendly UI labels
    """
    text = " ".join(categories)

    if "religion" in text:
        return "Place of Worship"
    if "natural.water" in categories:
        return "Lake / River"
    if "natural.forest" in categories:
        return "Forest Area"
    if "natural.mountain" in text:
        return "Mountain / Peak"
    if "heritage" in text:
        return "Heritage Site"
    return "Local Attraction"


async def geocode_location(location: str):
    """
    Step 1: Convert location name -> latitude & longitude
    """
    if not GEOAPIFY_API_KEY:
        raise RuntimeError("GEOAPIFY_API_KEY not set")

    params = {
        "text": location,
        "limit": 1,
        "apiKey": GEOAPIFY_API_KEY
    }

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.get(GEOAPIFY_GEOCODE_URL, params=params) as res:
            if res.status != 200:
                text = await res.text()
                raise RuntimeError(f"Geoapify geocode error {res.status}: {text}")

            data = await res.json()
            features = data.get("features", [])

            if not features:
                return None, None

            coords = features[0]["geometry"]["coordinates"]
            lon, lat = coords[0], coords[1]

            return lat, lon


async def search_village_experiences(lat: float, lon: float, radius_m: int = 50000):
    """
    Step 2: Fetch nearby village / rural / natural / cultural experiences
    """

    if not GEOAPIFY_API_KEY:
        raise RuntimeError("GEOAPIFY_API_KEY not set")

    params = {
        "categories": ",".join([
            "tourism.sights",
            "heritage",
            "natural",
            "leisure.park",
            "entertainment.museum",
            "religion.place_of_worship"
        ]),
        "filter": f"circle:{lon},{lat},{radius_m}",
        "bias": f"proximity:{lon},{lat}",
        "limit": 50,   # fetch more, we will filter + trim later
        "apiKey": GEOAPIFY_API_KEY
    }

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.get(GEOAPIFY_PLACES_URL, params=params) as res:
            if res.status != 200:
                text = await res.text()
                raise RuntimeError(f"Geoapify places error {res.status}: {text}")

            data = await res.json()
            features = data.get("features", [])

            results = []

            for f in features:
                props = f.get("properties", {})
                geom = f.get("geometry", {})
                coords = geom.get("coordinates", [None, None])

                name = props.get("name")
                categories = props.get("categories", [])
                distance = props.get("distance")

                # ✅ Skip unnamed forests (your requirement)
                if "natural.forest" in categories and not name:
                    continue

                # Build clean item
                results.append({
                    "name": name or "Local Attraction",
                    "category": categories,
                    "type": label_from_category(categories),   # friendly tag
                    "address": props.get("formatted"),
                    "lat": coords[1],
                    "lon": coords[0],
                    "distance_m": distance,
                    "source": "geoapify"
                })

            # ✅ Sort by nearest first
            results.sort(key=lambda x: x.get("distance_m", 10**9))

            # ✅ Limit for UI
            results = results[:10]

            return results


async def get_village_experiences(location: str):
    """
    Main function used by API:
    location -> lat/lon -> nearby village experiences
    """

    # 1. Geocode
    lat, lon = await geocode_location(location)

    if lat is None or lon is None:
        return {
            "location": location,
            "error": "Location not found",
            "experiences": []
        }

    # 2. Search nearby experiences
    experiences = await search_village_experiences(lat, lon)

    return {
        "location": location,
        "latitude": lat,
        "longitude": lon,
        "count": len(experiences),
        "experiences": experiences
    }
