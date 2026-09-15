# Voyayaha stable backend release

This backend is based on the known-working `3.1-global-place-gated` Hidden Places release.

## Deliberate stability choice
- Hidden Places discovery remains `3.1-global-place-gated`.
- Reddit + YouTube discovery, place gating, geocoding and 100 km filtering are unchanged.
- No Supabase/database fallback was inserted into this release, to avoid changing the known-working Hidden Places behavior.
- Travel Memories are a WordPress/frontend function and are not routed through this backend.

## Required environment variables for Hidden Places
- `GROQ_API_KEY` or `VY_GROQ_API_KEY`
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`
- `YOUTUBE_API_KEY`

The health endpoint is:
`/social-discovery/health`

Expected discovery version:
`3.1-global-place-gated`
