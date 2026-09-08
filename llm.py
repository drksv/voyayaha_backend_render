import json, os, requests
from dotenv import load_dotenv
load_dotenv()
GROQ_KEY=os.getenv("VY_GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
GROQ_URL="https://api.groq.com/openai/v1/chat/completions"
MODEL=os.getenv("VY_GROQ_MODEL") or os.getenv("VY_HIDDEN_GROQ_MODEL") or "llama-3.1-8b-instant"

def extract_json(text):
    try:
        v=json.loads(text)
        return v
    except Exception: pass
    for left,right in [("[","]"),("{","}")]:
        a=text.find(left); b=text.rfind(right)
        if a>=0 and b>a:
            try:return json.loads(text[a:b+1])
            except Exception:pass
    return []

def generate_itinerary(prompt):
    if not GROQ_KEY:return []
    try:
        r=requests.post(GROQ_URL,json={
            "model":MODEL,
            "messages":[{"role":"system","content":"Return only valid JSON. Follow the requested schema exactly."},{"role":"user","content":prompt}],
            "temperature":0.2,"max_tokens":3000
        },headers={"Authorization":f"Bearer {GROQ_KEY}","Content-Type":"application/json"},timeout=45)
        r.raise_for_status()
        return extract_json(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print("Groq itinerary error:",repr(e)); return []
