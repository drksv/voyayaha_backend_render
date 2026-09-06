import httpx
import os
from dotenv import load_dotenv

load_dotenv()
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY")

async def get_custom_travel_risk(country: str):
    try:
        url = "https://gnews.io/api/v4/search"
        params = {
            "q": f"{country} travel OR {country} safety OR {country} unrest",
            "lang": "en",
            "token": GNEWS_API_KEY,
            "max": 10
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            headlines = [article["title"] for article in data["articles"]]
            content_summary = " | ".join(headlines)

            # Simple scoring logic (demo only)
            risk_score = 1.0  # default low risk
            risk_keywords = ["protest", "riot", "unrest", "emergency", "alert", "ban", "evacuation"]

            if any(kw in content_summary.lower() for kw in risk_keywords):
                risk_score = 4.0  # higher risk

            return {
                "risk_level": risk_score,
                "message": f"Top news: {headlines[:3]}"
            }

    except Exception as e:
        print("Custom Travel Risk Error:", e)
        return {
            "risk_level": "Unknown",
            "message": "Could not fetch risk data."
        }

