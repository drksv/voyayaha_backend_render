# Voyayaha Social Discovery

## What Hidden Places does

A query such as `hidden villages in Pune` is processed as:

1. Geocode Pune to establish the center point.
2. Search Reddit across Reddit for recent/relevant discussions.
3. Search YouTube using relevance, recent uploads, and popularity.
4. Collect post text/comments and YouTube titles/descriptions/statistics.
5. Ask the LLM to extract actual place names from that supplied evidence. The LLM is not allowed to invent candidates.
6. Geocode each candidate and calculate the actual great-circle distance from the city center.
7. Discard candidates outside the requested radius (default 100 km).
8. Rank candidates using social evidence, recency, engagement, cross-source support, relevance and distance.
9. Ask the LLM to synthesize the evidence for the strongest candidates into the final top 3.
10. Return the place cards first; Reddit/YouTube URLs are supporting evidence in the expandable section.

## APIs / keys

For the full social feature, you need:
- `YOUTUBE_API_KEY`
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `VY_GROQ_API_KEY`

No separate paid geocoding API is required. The implementation uses Open-Meteo geocoding first and Nominatim as a fallback. These public services can rate-limit; the application degrades gracefully.

The LLM receives search evidence, not arbitrary URLs, and is instructed to only extract places actually present in that evidence. Geographic distance is calculated by the backend, not by the LLM.

## UI behavior in this release

The Hidden Places page calls only `/social-discovery` for search results. It no longer renders the legacy raw Reddit/YouTube search grid or the static `Places to explore` grid on the Hidden Places page.

For a city such as `Pune`, or a request such as `peaceful places in Mumbai`, the frontend asks for `limit=3` and renders the three highest-ranked geographically verified places. Supporting Reddit/YouTube links remain inside each place card under `See supporting evidence`.

The backend also supplements a short LLM candidate list with conservative source-text extraction, retries candidate geocoding with several query forms, and fills missing synthesis slots from the already verified ranked candidates. It never labels a raw social URL as a place recommendation.
