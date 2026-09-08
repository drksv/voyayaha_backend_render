import os, httpx
from dotenv import load_dotenv
load_dotenv()
WEATHERAPI_KEY=os.getenv("WEATHERAPI_KEY")
async def get_weather_and_risk(location:str):
    if not WEATHERAPI_KEY:
        return {"location":location,"summary":"Weather unavailable","temperature_c":None,"indoor_preferred":False,"source":"fallback"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r=await client.get("https://api.weatherapi.com/v1/current.json",
                               params={"key":WEATHERAPI_KEY,"q":location,"aqi":"no"})
            r.raise_for_status(); d=r.json()
            condition=d["current"]["condition"]["text"].lower()
            return {"location":location,"summary":condition.title(),"temperature_c":d["current"]["temp_c"],
                    "indoor_preferred":any(w in condition for w in ["rain","snow","storm","fog","drizzle","wind"]),"source":"weatherapi"}
    except Exception as e:
        print("Weather error:",repr(e))
        return {"location":location,"summary":"Weather unavailable","temperature_c":None,"indoor_preferred":False,"source":"fallback"}
