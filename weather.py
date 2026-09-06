import os, httpx
from dotenv import load_dotenv

load_dotenv()
WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")

async def get_weather_and_risk(location: str):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            url = "https://api.weatherapi.com/v1/current.json"  # HTTPS
            params = {
                "key": WEATHERAPI_KEY,
                "q": location,
                "aqi": "no"
            }

            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()

            condition = data["current"]["condition"]["text"].lower()
            temp_c = data["current"]["temp_c"]

            indoor_preferred = any(word in condition for word in [
                "rain", "snow", "storm", "fog", "drizzle", "wind"
            ])

            return {
                "summary": condition.title(),
                "temperature_c": temp_c,
                "indoor_preferred": indoor_preferred
            }

    except Exception as e:
        print("WeatherAPI error:", e)
        return {
            "summary": "Unknown",
            "temperature_c": None,
            "indoor_preferred": True
        }
