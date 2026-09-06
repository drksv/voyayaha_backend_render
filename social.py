# social.py
import os
import httpx
import praw
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()

# -----------------------------
# ENV (safe loading)
# -----------------------------
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")

# -----------------------------
# REDDIT CLIENT (optional)
# -----------------------------
reddit = None
if all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT]):
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT
    )

# -----------------------------
# IMAGE PROXY
# -----------------------------
API_BASE = os.getenv("API_BASE", "https://backend-eqzz.onrender.com")

def proxify(url: str):
    return f"{API_BASE}/img?url={quote_plus(url)}" if url else None

# -----------------------------
# REDDIT
# -----------------------------
async def get_reddit_posts(query: str, limit: int = 5):
    if not reddit:
        return []  # Safe fallback if Reddit not configured

    results = []

    try:
        for post in reddit.subreddit("travel").search(query, limit=limit, sort="relevance"):
            image = None

            if hasattr(post, "preview"):
                imgs = post.preview.get("images", [])
                if imgs:
                    image = imgs[0]["source"]["url"]

            if not image and post.thumbnail and post.thumbnail.startswith("http"):
                image = post.thumbnail

            results.append({
                "source": "reddit",
                "title": post.title,
                "description": post.selftext[:200] if post.selftext else f"From r/{post.subreddit}",
                "image": proxify(image),
                "url": f"https://www.reddit.com{post.permalink}"
            })

    except Exception as e:
        # Never crash API because of Reddit
        return []

    return results

# -----------------------------
# YOUTUBE
# -----------------------------
async def get_youtube_posts(query: str, limit: int = 5):
    if not YOUTUBE_API_KEY:
        return []  # Safe fallback if key missing

    q = quote_plus(query)
    url = (
        "https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&type=video&maxResults={limit}"
        f"&q={q}&key={YOUTUBE_API_KEY}"
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()

        results = []
        for item in data.get("items", []):
            s = item["snippet"]
            vid = item["id"]["videoId"]

            results.append({
                "source": "youtube",
                "title": s["title"],
                "description": s["description"][:200],
                "image": proxify(s["thumbnails"]["medium"]["url"]),
                "url": f"https://www.youtube.com/watch?v={vid}"
            })

        return results

    except Exception:
        # Never crash API because of YouTube
        return []
