import aiohttp, os
GEOAPIFY_API_KEY=os.getenv("GEOAPIFY_API_KEY")
def label_from_category(categories):
    text=" ".join(categories or [])
    if "religion" in text:return "Place of Worship"
    if "natural.water" in categories:return "Lake / River"
    if "natural.forest" in categories:return "Forest Area"
    if "natural.mountain" in text:return "Mountain / Peak"
    if "heritage" in text:return "Heritage Site"
    return "Local Attraction"
async def get_village_experiences(location):
    if not GEOAPIFY_API_KEY:
        return {"location":location,"latitude":None,"longitude":None,"count":0,"experiences":[],"source":"fallback"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get("https://api.geoapify.com/v1/geocode/search",params={"text":location,"limit":1,"apiKey":GEOAPIFY_API_KEY}) as r:
                r.raise_for_status(); d=await r.json()
            fs=d.get("features",[])
            if not fs:return {"location":location,"latitude":None,"longitude":None,"count":0,"experiences":[]}
            lon,lat=fs[0]["geometry"]["coordinates"]
            params={"categories":"tourism.sights,heritage,natural,leisure.park,entertainment.museum,religion.place_of_worship",
                    "filter":f"circle:{lon},{lat},50000","bias":f"proximity:{lon},{lat}","limit":50,"apiKey":GEOAPIFY_API_KEY}
            async with s.get("https://api.geoapify.com/v2/places",params=params) as r:
                r.raise_for_status(); data=await r.json()
        out=[]
        for f in data.get("features",[]):
            p=f.get("properties",{}); c=p.get("categories",[]); coords=f.get("geometry",{}).get("coordinates",[None,None])
            if "natural.forest" in c and not p.get("name"):continue
            out.append({"name":p.get("name") or "Local Attraction","category":c,"type":label_from_category(c),
                        "address":p.get("formatted"),"lat":coords[1],"lon":coords[0],"distance_m":p.get("distance"),"source":"geoapify"})
        out.sort(key=lambda x:x.get("distance_m") or 10**9)
        return {"location":location,"latitude":lat,"longitude":lon,"count":len(out[:10]),"experiences":out[:10]}
    except Exception as e:
        print("Village error:",repr(e))
        return {"location":location,"latitude":None,"longitude":None,"count":0,"experiences":[],"degraded":True}
