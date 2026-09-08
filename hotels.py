import os, httpx
TP_TOKEN=os.getenv("T_PAYOUTS_TOKEN")
async def search_hotels(city, check_in="", check_out="", limit=6):
    if not TP_TOKEN or not check_in or not check_out:
        return []
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r=await client.get("https://engine.hotellook.com/api/v2/cache.json",
                params={"location":city,"checkIn":check_in,"checkOut":check_out,"limit":limit,"token":TP_TOKEN})
            r.raise_for_status(); raw=r.json()
        if not isinstance(raw,list): return []
        return [{"name":x.get("hotelName","Untitled"),"rating":x.get("stars"),"price":x.get("priceFrom"),
                 "lat":x.get("location",{}).get("geo",{}).get("lat"),"lon":x.get("location",{}).get("geo",{}).get("lon")}
                for x in raw[:limit]]
    except Exception as e: print("Hotels error:",repr(e)); return []
