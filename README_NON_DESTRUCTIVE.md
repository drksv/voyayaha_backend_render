# Voyayaha Render Backend — Non-Destructive Revision

This folder is intended to be the GitHub repository root for the Render backend.

## Existing functionality preserved

The existing `llm.py`, `social.py`, `/chat/experiences`, `/social`, `/trends`, Village Tourism, Travel Intel, weather, hotels, and other existing modules were preserved.

## New endpoints

- `GET /chat/experiences-hidden?location=Pune&query=hidden%20places&limit=3`
  - Separate Hidden Places AI endpoint.
  - Returns `{ "stops": [...] }` with up to 3 recommendations.

- `GET /social-hidden?location=Mumbai&query=peaceful%20places&limit=3`
  - Separate Reddit + YouTube endpoint.
  - Uses the existing API credentials if present.

- `POST /travel-memory`
  - Separate multipart proxy for Travel Memories.
  - Forwards the submission to the existing WordPress endpoint:
    `/wp-json/voyayaha/v1/travel-memory`

## Render

Use this folder as the repository root. The existing Render service can continue using its current Python runtime and start command.

Keep all existing Render environment variables. Add `VOYAYAHA_WORDPRESS_URL=https://voyayaha.com` if desired; the code already defaults to that URL.

Do not put API keys into GitHub. Keep them in Render Environment Variables.
