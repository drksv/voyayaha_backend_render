import os, httpx
from dotenv import load_dotenv

load_dotenv()
KLIM_KEY = os.getenv("KLIMAPI_KEY")
API = "https://api.klimapi.com/estimate"


async def get_estimate_trip_co2(mode: str, distance_km: float):
    body = {"type": "travel", "scenario": {"transportation_mode": mode, "distance": distance_km}}
    headers = {"Authorization": f"Bearer {KLIM_KEY}"}
    async with httpx.AsyncClient() as client:
        r = await client.post(API, json=body, headers=headers)
        r.raise_for_status()
        return r.json()["co2e"]
