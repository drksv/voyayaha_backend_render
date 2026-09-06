def build_traveler_advice(traffic):
    advice = []

    if traffic.get("traffic_level") == "High":
        advice.append("Expect delays reaching popular attractions")

    elif traffic.get("traffic_level") == "Moderate":
        advice.append("Some congestion expected near tourist areas")

    else:
        advice.append("Traffic conditions are favorable for sightseeing")

    return " | ".join(advice)
