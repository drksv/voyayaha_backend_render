from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import json
from llm import generate_itinerary
from pydantic import BaseModel
from typing import Optional

# Only needed if run standalone
app = FastAPI()

# -----------------------------
# Models
# -----------------------------

class ExperienceRequest(BaseModel):
    location: str
    budget: Optional[str] = ""
    activity: Optional[str] = ""
    duration: str                # half_day | full_day | multi_day
    motivation: Optional[str] = ""
    num_days: Optional[int] = 1  # only used if multi_day

# -----------------------------
# Route registration
# -----------------------------

def register_chat_routes(app: FastAPI):

    # ❌ REMOVE THE GET ROUTE COMPLETELY
    # DO NOT DEFINE @app.get("/chat/experiences") HERE

    # ==========================================
    # POST route – for future daily itineraries
    # ==========================================
    @ app.post("/chat/experiences")
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
                total_experiences = 3
                days = 1
            else:
                experiences_per_day = 2
                days = max(1, num_days)
                total_experiences = days * experiences_per_day
    
            print("RECEIVED:", data)
            print("TOTAL EXPERIENCES:", total_experiences)
    
            prompt = f"""
    You are a travel assistant.
    
    User details:
    - Location: {location}
    - Budget: {budget}
    - Activity type: {activity}
    - Motivation: {motivation}
    - Trip duration: {days} days
    
    Rules:
    - If trip is 1 day or less, suggest exactly 3 experiences.
    - If trip is more than 1 day, suggest exactly 2 experiences per day.
    - Total number of experiences must be exactly {total_experiences}.
    
    Generate a JSON array of experiences.
    
    Each item must be:
    {{
      "title": "Marine Drive",
      "intro": "Morning walk by the sea.",
      "top_places": [
        {{"name": "Marine Drive", "tip": "Best at sunrise"}}
      ]
    }}
    
    Output only the JSON array. No explanation text.
    """
    
            llm_output = generate_itinerary(prompt)
    
            if isinstance(llm_output, list):
                experiences = llm_output
            else:
                cleaned = llm_output.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned.split("```json")[-1].split("```")[0].strip()
    
                experiences = json.loads(cleaned)
    
            # 🔒 Enforce exact count
            if len(experiences) > total_experiences:
                experiences = experiences[:total_experiences]
            elif len(experiences) < total_experiences:
                last = experiences[-1] if experiences else {
                    "title": "Explore the city",
                    "intro": f"Discover more of {location}.",
                    "top_places": []
                }
                while len(experiences) < total_experiences:
                    experiences.append(last)
    
            # ✅ IMPORTANT: match frontend expectation
            return {"stops": experiences}
    
        except Exception as e:
            print("ERROR:", e)
            return {"stops": [], "error": str(e)}
    
    
    

