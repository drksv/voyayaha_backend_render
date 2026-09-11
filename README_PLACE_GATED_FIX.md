# Voyayaha Hidden Places — place-gated fix

This version fixes false place names such as **Welcome**, **Dont**, **What**, and **Please**.

## What changed

1. Reddit + YouTube are still used as the evidence sources.
2. The LLM may propose candidate names, but it cannot make a candidate valid by itself.
3. Every candidate must have source evidence containing the candidate name.
4. Candidates are geocoded with Nominatim/Open-Meteo and must be classified as a geographic place/feature.
5. Single-word candidates need either geographic source context or an independently verified populated geographic feature.
6. The requested 100 km radius is checked with Haversine distance from the city centre.
7. Final cards include `geocoder_verified: true`.
8. The response includes `discovery_version: 3.0-place-gated` so an old Render deployment cannot silently feed the new frontend.
9. The frontend refuses to display results from an older backend or results without geocoder verification and source evidence.
10. Added a non-secret health endpoint: `/social-discovery/health`.

## Render environment variables to check

Required for the full social discovery:

- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`
- `YOUTUBE_API_KEY`
- `VY_GROQ_API_KEY` (or `GROQ_API_KEY`) for AI extraction/synthesis

Also keep:

- `CORS_ORIGINS=https://voyayaha.com,https://www.voyayaha.com,http://localhost:5173`
- `API_BASE=https://backend-eqzz.onrender.com`

The health endpoint reports only true/false for these keys; it never exposes their values.

## Deployment order

1. Deploy this backend ZIP to Render and wait for a successful deploy.
2. Open `https://YOUR-RENDER-SERVICE.onrender.com/social-discovery/health`.
3. Confirm `discovery_version` is `3.0-place-gated`.
4. Confirm `youtube_api`, `reddit_api`, and `groq` are `true` if you expect all three services.
5. Deploy the matching frontend ZIP.
6. Search `Pune` or `peaceful places in Mumbai`.

If the frontend says the backend is older, the wrong Render service/branch is still connected.
