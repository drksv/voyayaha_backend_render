# llm.py
import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

VY_GROQ_API_KEY = os.getenv("VY_GROQ_API_KEY")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def extract_json(text: str):
    """
    Safely extract JSON from LLM output even if extra text is present.
    """
    try:
        # If already pure JSON
        return json.loads(text)
    except:
        pass

    # Try to extract first JSON block
    try:
        start = text.find("[")
        end = text.rfind("]") + 1
        if start != -1 and end != -1:
            cleaned = text[start:end]
            return json.loads(cleaned)
    except:
        pass

    # Final fallback
    return [
        {
            "title": "AI Suggestion",
            "description": text.strip()
        }
    ]


def generate_itinerary(prompt: str):
    if not VY_GROQ_API_KEY:
        # Safe fallback if key missing
        return [
            {
                "title": "Explore the City",
                "description": "Visit popular attractions and local highlights."
            },
            {
                "title": "Food Experience",
                "description": "Try famous local cuisine and street food."
            }
        ]

    headers = {
        "Authorization": f"Bearer {VY_GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {
                "role": "system",
                "content": "You are a travel planner. Always output a JSON array of objects with title and description only. No extra text."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.4,
        "max_tokens": 800
    }

    try:
        r = requests.post(GROQ_URL, json=body, headers=headers, timeout=30)

        if r.status_code != 200:
            raise ValueError(f"Groq API error: {r.text}")

        content = r.json()["choices"][0]["message"]["content"]

        # Robust JSON extraction
        return extract_json(content)

    except Exception as e:
        # Hard fallback so frontend never breaks
        return [
            {
                "title": "City Highlights",
                "description": "Top places to visit in your selected destination."
            },
            {
                "title": "Local Experience",
                "description": "Cultural and food experiences recommended for you."
            }
        ]
