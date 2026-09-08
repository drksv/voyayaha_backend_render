import os, requests
from dotenv import load_dotenv
load_dotenv()
OPENWEATHER = os.getenv("OPENWEATHER")

def get_lat_lon_from_city(city: str):
    try:
        r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": city, "count": 1, "language": "en", "format": "json"},
                         timeout=10)
        r.raise_for_status(); data = r.json()
        if data.get("results"): return data["results"][0]["latitude"], data["results"][0]["longitude"]
    except Exception as e: print("geocoding error:", repr(e))
    return None, None

def get_weather_16_days(lat: float, lon: float):
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude":lat,"longitude":lon,
            "daily":"temperature_2m_max,temperature_2m_min,weathercode,rain_sum,windspeed_10m_max",
            "forecast_days":16,"timezone":"auto"}, timeout=10)
        r.raise_for_status(); daily=r.json().get("daily",{})
        return [{"date":daily["time"][i],"max_temp":daily["temperature_2m_max"][i],
                 "min_temp":daily["temperature_2m_min"][i],"weather_code":daily["weathercode"][i],
                 "rain_mm":daily["rain_sum"][i],"wind_kmph":daily["windspeed_10m_max"][i]}
                for i in range(len(daily.get("time",[])))]
    except Exception as e: print("forecast error:", repr(e)); return []

def get_aqi(city=None, lat=None, lon=None):
    if lat is None or lon is None or not OPENWEATHER:
        return {"aqi":"N/A","health_note":"AQI service unavailable"}
    try:
        r=requests.get("https://api.openweathermap.org/data/2.5/air_pollution",
                       params={"lat":lat,"lon":lon,"appid":OPENWEATHER},timeout=10)
        r.raise_for_status(); data=r.json(); item=(data.get("list") or [None])[0]
        if not item: return {"aqi":"N/A","health_note":"No AQI data available"}
        idx=item.get("main",{}).get("aqi"); labels={1:"Good",2:"Fair",3:"Moderate",4:"Poor",5:"Very Poor"}
        return {"aqi":idx,"health_note":labels.get(idx,"Unknown")}
    except Exception as e: print("AQI error:", repr(e)); return {"aqi":"N/A","health_note":"AQI service unavailable"}
