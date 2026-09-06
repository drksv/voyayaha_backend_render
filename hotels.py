"""Thin wrapper for Travelpayouts hotel search."""
import os, httpx

TP_TOKEN = os.getenv("T_PAYOUTS_TOKEN")

async def search_hotels(city: str, check_in: str, check_out: str, limit: int = 6):
    url = "https://engine.hotellook.com/api/v2/cache.json"
    params = {
        "location": city,
        "checkIn": check_in,
        "checkOut": check_out,
        "limit": limit,
        "token": TP_TOKEN,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        #return r.json()
        raw_results = r.json()
    
    # 👇 Add this to inspect structure
        results = []
        for item in raw_results:
            results.append({
                "name": item.get("hotelName", "Untitled"),
                "rating": item.get("stars", None),
                "price": item.get("priceFrom", None),
                "lat": item.get("location", {}).get("geo", {}).get("lat"),
                "lon": item.get("location", {}).get("geo", {}).get("lon"),
            })

        return results
