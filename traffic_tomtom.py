import requests
import os

TOMTOMKEY = os.getenv("TOMTOMKEY")

def get_traffic_status(lat: float, lon: float):
    url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
    params = {
        "point": f"{lat},{lon}",
        "key": TOMTOMKEY
    }

    try:
        r = requests.get(url, params=params, timeout=10).json()
        data = r.get("flowSegmentData")

        if not data:
            return {"status": "Unavailable"}

        current_speed = data["currentSpeed"]
        free_flow = data["freeFlowSpeed"]

        ratio = current_speed / free_flow if free_flow else 1

        if ratio > 0.8:
            level = "Low"
            delay = "Minimal"
        elif ratio > 0.5:
            level = "Moderate"
            delay = "Possible delays"
        else:
            level = "High"
            delay = "Likely delays"

        return {
            "traffic_level": level,
            "current_speed_kmph": current_speed,
            "free_flow_speed_kmph": free_flow,
            "delay_advice": delay
        }

    except Exception:
        return {"status": "Unavailable"}
