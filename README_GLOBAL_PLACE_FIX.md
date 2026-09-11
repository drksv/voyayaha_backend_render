# Voyayaha Hidden Places — Global Place-Gated Fix 3.1

This revision removes the India-only geocoding restriction. Hidden Places discovery is now global: the city supplied by the user controls the geographic search.

## What changed
- Removed Nominatim `countrycodes=in`.
- Removed Open-Meteo country-code filtering to India.
- Removed automatic `India` / `Maharashtra` suffixes from candidate geocoding.
- Backend no longer defaults a missing location to `India`.
- Kept strict geographic class/type validation so generic words are not accepted as destinations.
- Frontend now requires `discovery_version=3.1-global-place-gated`.

## Deploy both
1. Deploy this backend ZIP to Render.
2. Confirm `/social-discovery/health` returns `discovery_version` = `3.1-global-place-gated` and all required configuration booleans are true.
3. Deploy the matching frontend ZIP.
4. Test with cities outside India, for example `peaceful places in Boston`, `hidden villages near London`, or `offbeat places in Lisbon`.

The service still uses Reddit + YouTube evidence and geocoding; it does not assume India.
