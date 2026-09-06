import requests
import os

OPENWEATHER = os.getenv("OPENWEATHER")

def get_lat_lon_from_city(city: str):
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": city,
        "count": 1,
        "language": "en",
        "format": "json"
    }

    r = requests.get(url, params=params, timeout=10).json()

    if "results" not in r or not r["results"]:
        return None, None

    return r["results"][0]["latitude"], r["results"][0]["longitude"]


def get_weather_16_days(lat: float, lon: float):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": (
            "temperature_2m_max,"
            "temperature_2m_min,"
            "weathercode,"
            "rain_sum,"
            "windspeed_10m_max"
        ),
        "forecast_days": 16,
        "timezone": "auto"
    }

    r = requests.get(url, params=params, timeout=10).json()

    daily = r.get("daily", {})

    forecast = []
    for i in range(len(daily.get("time", []))):
        forecast.append({
            "date": daily["time"][i],
            "max_temp": daily["temperature_2m_max"][i],
            "min_temp": daily["temperature_2m_min"][i],
            "weather_code": daily["weathercode"][i],
            "rain_mm": daily["rain_sum"][i],
            "wind_kmph": daily["windspeed_10m_max"][i],
        })

    return forecast

# ---------- AQI ----------
def get_aqi(city: str = None, lat: float = None, lon: float = None):
    if not OPENWEATHER:
        return {
            "aqi": "N/A",
            "health_note": "AQI service unavailable"
        }

    if lat is None or lon is None:
        return {
            "aqi": "N/A",
            "health_note": "Location not found"
        }

    url = "https://api.openweathermap.org/data/2.5/air_pollution"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": OPENWEATHER
    }

    r = requests.get(url, params=params, timeout=10).json()

    if "list" not in r or not r["list"]:
        return {
            "aqi": "N/A",
            "health_note": "No AQI data available"
        }

    aqi_index = r["list"][0]["main"]["aqi"]

    aqi_map = {
        1: "Good",
        2: "Fair",
        3: "Moderate",
        4: "Poor",
        5: "Very Poor"
    }

    return {
        "aqi": aqi_index,
        "health_note": aqi_map.get(aqi_index, "Unknown")
    }
