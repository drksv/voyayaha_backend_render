# Voyayaha Backend — stable API contract
Deploy as a Render Web Service with:
- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Runtime: Python 3.11.9

All optional provider failures degrade to local/empty results instead of HTTP 500.
Frontend should use its same-origin `/api/*` proxy routes; direct backend access is also supported by CORS.
