# Voyayaha Hidden Places — AI + Reddit + YouTube

The Hidden Places endpoint now uses a three-stage pipeline:

1. **Live discovery** — searches Reddit and YouTube for the requested city/query.
2. **AI synthesis** — sends the live evidence to the same Groq/OpenAI-compatible LLM configuration used by `llm.py`, through `voyayaha_hidden_llm.py` so the existing itinerary contract remains untouched.
3. **Evidence-grounded output** — the LLM selects up to exactly 3 places and returns source URLs. It is instructed not to invent places that are not supported by the retrieved social evidence.

## Endpoint

`GET /chat/experiences-hidden?location=Pune&query=hidden%20places%20near%20Pune&limit=3`

Aliases:
- `GET /hidden-experiences`
- `GET /social-hidden` (raw normalized Reddit/YouTube evidence)

The AI endpoint returns:

```json
{
  "stops": [
    {
      "name": "...",
      "description": "...",
      "tip": "...",
      "category": "...",
      "source": "reddit, youtube",
      "source_url": "https://...",
      "image": "...",
      "evidence": "..."
    }
  ],
  "places": [],
  "results": [],
  "sources": {"reddit": 0, "youtube": 0},
  "ai_ranked": true,
  "location": "Pune",
  "query": "hidden places near Pune"
}
```

## Render environment variables

Required for the complete pipeline:

```env
VY_GROQ_API_KEY=...
VY_GROQ_MODEL=llama-3.1-8b-instant
YOUTUBE_API_KEY=...
```

Recommended Reddit credentials:

```env
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=voyayaha/1.0
```

Reddit also has a public JSON fallback, so a missing Reddit credential does not crash the endpoint. YouTube requires a valid API key for live YouTube search.

## Frontend

The compatible frontend now unwraps the backend's `/social-hidden` response so the existing Reddit/YouTube cards continue to work.
