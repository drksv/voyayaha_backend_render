import requests
import os

FOURSQUARE_API_KEY = os.getenv("FOURSQUARE_API_KEY")

def get_crowd_estimate(city: str, limit: int = 10):
    url = "https://api.foursquare.com/v3/places/search"
    headers = {"Authorization": FOURSQUARE_API_KEY}
    params = {"near": city, "limit": limit}

    r = requests.get(url, headers=headers, params=params).json()

    scores = []

    for place in r.get("results", []):
        if "popularity" in place:
            scores.append(place["popularity"])

    avg = sum(scores) / len(scores) if scores else 0

    if avg > 70:
        level = "High"
    elif avg > 40:
        level = "Moderate"
    else:
        level = "Low"

    return {
        "average_popularity": round(avg, 2),
        "crowd_level": level
    }
