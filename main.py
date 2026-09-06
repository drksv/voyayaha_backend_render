from fastapi import FastAPI, HTTPException, Query, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from urllib.parse import unquote
import httpx
from dotenv import load_dotenv
import os
import copy
import json
import requests
import pymysql
import os
from typing import List

from hotels import search_hotels
from social import get_youtube_posts, get_reddit_posts
from experiences import get_combined_experiences
from llm import generate_itinerary
from weather import get_weather_and_risk

from pydantic import BaseModel
from typing import Optional
from villageexperiences import get_village_experiences
from weather_openmeteo import (
    get_weather_16_days,
    get_lat_lon_from_city,
    get_aqi
)
from traveler_advice import build_traveler_advice
from traffic_tomtom import get_traffic_status

# Non-destructive Voyayaha additions. Existing llm.py/social.py endpoints remain unchanged.
from voyayaha_hidden_llm import generate_hidden_itinerary
from voyayaha_hidden_social import get_hidden_social







load_dotenv()

app = FastAPI(title="Voyayaha – AI Travel Concierge")


# -----------------------------
# CORS
# -----------------------------
origins = [
    "https://voyayaha.lovable.app",
    "https://voyayaha.lovestoblog.com",
    "https://voyayaha.com",
    "https://www.voyayaha.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
    "http://localhost:8080",
    "http://10.0.0.101:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# -----------------------------
# MODELS
# -----------------------------
class ExperienceRequest(BaseModel):
    location: str
    budget: Optional[str] = ""
    activity: Optional[str] = ""
    duration: str                # half_day | full_day | multi_day
    motivation: Optional[str] = ""
    num_days: Optional[int] = 1  # only used if multi_day


# -----------------------------
# CHAT / FRONTEND RECOMMENDATIONS
# -----------------------------
@app.post("/chat/experiences")
async def chat_experiences_post(data: ExperienceRequest):
    try:
        location = data.location
        budget = data.budget or ""
        activity = data.activity or ""
        duration = data.duration
        motivation = data.motivation or ""
        num_days = data.num_days or 1

        # 🧠 Decide experiences per day
        if duration in ["half_day", "full_day"]:
            experiences_per_day = 3
            days = 1
        else:
            experiences_per_day = 2
            days = max(1, num_days)

        total_experiences = days * experiences_per_day

        print("RECEIVED:", data)
        print("TOTAL EXPERIENCES:", total_experiences)

        prompt = f"""
You are Voyayaha AI Travel Guide.

The user is visiting: {location}

User preferences:
Budget: {budget}
Activity: {activity}
Motivation: {motivation}
Trip duration: {days} days

Your task:
Generate a multi-day itinerary in CITY GUIDE style.

Rules:
- For each day, generate exactly {experiences_per_day} recommendations.
- Total items must be exactly {total_experiences}.
- Each item MUST include:
    - day: day number (1, 2, 3...)
    - title: short heading for that experience block
    - intro: 1–2 lines describing what people enjoy
    - top_places: array of exactly 3 objects:
        - name
        - tip

Example format:

[
  {{
    "day": 1,
    "title": "Bangkok Relaxation Day",
    "intro": "Unwind in Bangkok’s green and wellness spots.",
    "top_places": [
      {{"name": "Lumphini Park", "tip": "Relax with a walk and lake views."}},
      {{"name": "Suan Rot Fai Park", "tip": "Enjoy gardens and cycling tracks."}},
      {{"name": "Mandara Spa", "tip": "Rejuvenate with a traditional Thai massage."}}
    ]
  }}
]

IMPORTANT:
- Use REAL places in {location}.
- Return ONLY valid JSON array. No extra text.
"""

        llm_output = generate_itinerary(prompt)

        # -----------------------------
        # Parse LLM output safely
        # -----------------------------
        if isinstance(llm_output, list):
            experiences = llm_output
        else:
            cleaned = llm_output.strip()

            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]

            experiences = json.loads(cleaned)

        # -----------------------------
        # 🔒 Enforce exact count WITHOUT repeating same object
        # -----------------------------
        if len(experiences) > total_experiences:
            experiences = experiences[:total_experiences]

       

        return {"stops": experiences}

    except Exception as e:
        print("ERROR in /chat/experiences:", e)
        return {"stops": [], "error": str(e)}



# -----------------------------
# HIDDEN PLACES / PEACEFUL SEARCH (NON-DESTRUCTIVE ADDITION)
# -----------------------------
@app.get("/chat/experiences-hidden")
async def chat_experiences_hidden(
    location: str,
    query: str = "",
    limit: int = 3,
):
    """Separate endpoint for the new Hidden Places explorer.
    Does not alter the existing /chat/experiences endpoint.
    """
    results = generate_hidden_itinerary(location, query, limit)
    return {"stops": results}


@app.get("/social-hidden")
async def social_hidden(
    location: str = "Mumbai",
    query: str = "",
    limit: int = 3,
):
    """Separate Reddit + YouTube endpoint for the new Hidden Places explorer."""
    return await get_hidden_social(location, query, limit)


# -----------------------------
# TRAVEL MEMORY WORDPRESS PROXY (NON-DESTRUCTIVE ADDITION)
# -----------------------------
@app.post("/travel-memory")
async def travel_memory_proxy(
    title: str = Form(...),
    location: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    date: str = Form(""),
    description: str = Form(""),
    photo: UploadFile | None = File(None),
):
    """Forward Travel Memory submissions to the existing WordPress moderation API.
    This keeps the WordPress plugin as the storage/moderation layer and avoids
    requiring the browser to POST multipart data directly to WordPress.
    """
    wordpress_base = os.getenv("VOYAYAHA_WORDPRESS_URL", "https://voyayaha.com").rstrip("/")
    endpoint = f"{wordpress_base}/wp-json/voyayaha/v1/travel-memory"

    data = {
        "title": title,
        "location": location,
        "latitude": str(latitude),
        "longitude": str(longitude),
        "date": date,
        "description": description,
    }
    files = None
    file_bytes = None
    if photo is not None:
        file_bytes = await photo.read()
        files = {
            "photo": (
                photo.filename or "travel-memory.jpg",
                file_bytes,
                photo.content_type or "application/octet-stream",
            )
        }

    try:
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.post(endpoint, data=data, files=files)
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = response.json()
        else:
            payload = {"message": response.text}
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=payload)
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        print("ERROR in /travel-memory:", exc)
        raise HTTPException(status_code=502, detail="Could not reach the Voyayaha WordPress Travel Memory API.")


# -----------------------------
# ROOT
# -----------------------------
@app.get("/")
def root():
    return {"status": "Voyayaha backend running"}


# -----------------------------
# IMAGE PROXY
# -----------------------------
@app.get("/img")
async def proxy_image(url: str):
    decoded = unquote(url)

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        r = await client.get(decoded)
        r.raise_for_status()

        return Response(
            content=r.content,
            media_type=r.headers.get("content-type", "image/jpeg"),
            headers={"Cache-Control": "public, max-age=86400"}
        )


# -----------------------------
# EXPERIENCES (RAW DATA)
# -----------------------------
@app.get("/experiences")
async def experiences(location: str, query: str = "tourist"):
    """
    Returns weather, Yelp results, Geoapify fallback results.
    """
    return await get_combined_experiences(location, query)


# -----------------------------
# HOTELS
# -----------------------------
@app.get("/hotels")
async def hotels(city: str, check_in: str, check_out: str, limit: int = 6):
    return await search_hotels(city, check_in, check_out, limit)


# -----------------------------
# WEATHER
# -----------------------------
@app.get("/weather")
async def weather(location: str):
    return await get_weather_and_risk(location)


# -----------------------------
# SOCIAL
# -----------------------------
@app.get("/social")
async def social(location: str = "Mumbai", limit: int = 5):
    reddit_posts = await get_reddit_posts(location, limit)
    youtube_posts = await get_youtube_posts(location, limit)
    return youtube_posts + reddit_posts


# -----------------------------
# TRENDS
# -----------------------------
@app.get("/trends")
async def trends(location: str = "Pune"):
    query = f"{location} travel OR {location} places OR {location} itinerary"
    return await get_reddit_posts(query, limit=8)

@app.get("/village/experiences")
async def village_experiences(
    location: str = Query(..., description="Village / town / place name")
):
    """
    Example:
    /village/experiences?location=Ranikhet
    """

    try:
        result = await get_village_experiences(location)
        return result

    except Exception as e:
        return {
            "location": location,
            "error": str(e),
            "experiences": []
        }

@app.get("/travel-intel")
def travel_intel(city: str):
    lat, lon = get_lat_lon_from_city(city)
    if not lat or not lon:
        raise HTTPException(status_code=404, detail="City not found")

    weather = get_weather_16_days(lat, lon)
    aqi = get_aqi(city=city, lat=lat, lon=lon)
    traffic = get_traffic_status(lat, lon)

    traveler_advice = build_traveler_advice(traffic)

    return {
        "city": city,
        "coordinates": {
            "latitude": lat,
            "longitude": lon
        },
        "weather_16_day_forecast": weather,
        "air_quality": aqi,
        "traffic": traffic,
        "traveler_advice": traveler_advice
    }

