from datetime import datetime

def estimate_crowd(location_type: str):
    hour = datetime.now().hour
    weekday = datetime.now().weekday()  # 0=Mon, 6=Sun

    crowd = "Low"

    if location_type == "mall":
        if 17 <= hour <= 21:
            crowd = "High"

    elif location_type == "beach":
        if weekday >= 5 and (6 <= hour <= 10 or 16 <= hour <= 19):
            crowd = "High"

    elif location_type == "monument":
        if 10 <= hour <= 16:
            crowd = "Moderate"

    elif location_type == "market":
        if 18 <= hour <= 22:
            crowd = "High"

    return {
        "crowd_level": crowd,
        "based_on": "time-based travel patterns"
    }
