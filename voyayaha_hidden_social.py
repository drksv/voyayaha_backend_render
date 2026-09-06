"""Non-destructive Reddit/YouTube helper for Hidden Places discovery.
Does not modify or replace the existing social.py module.
"""
import os
from urllib.parse import quote_plus
import httpx
import praw
from dotenv import load_dotenv

load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
API_BASE = os.getenv("API_BASE", "https://backend-eqzz.onrender.com").rstrip("/")

_reddit = None
if all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT]):
    _reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
    )


def _proxify(url: str | None):
    return f"{API_BASE}/img?url={quote_plus(url)}" if url else None


async def _reddit(query: str, limit: int):
    if not _reddit:
        return []
    results = []
    try:
        for post in _reddit.subreddit("travel").search(query, limit=limit, sort="relevance"):
            image = None
            if hasattr(post, "preview"):
                images = post.preview.get("images", [])
                if images:
                    image = images[0].get("source", {}).get("url")
            if not image and getattr(post, "thumbnail", "").startswith("http"):
                image = post.thumbnail
            results.append({
                "source": "reddit",
                "title": post.title,
                "description": (post.selftext[:200] if post.selftext else f"From r/{post.subreddit}"),
                "image": _proxify(image),
                "url": f"https://www.reddit.com{post.permalink}",
            })
    except Exception as exc:
        print("ERROR in hidden Reddit search:", exc)
    return results


async def _youtube(query: str, limit: int):
    if not YOUTUBE_API_KEY:
        return []
    url = (
        "https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&type=video&maxResults={limit}"
        f"&q={quote_plus(query)}&key={YOUTUBE_API_KEY}"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        results = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            thumb = snippet.get("thumbnails", {}).get("medium", {}).get("url")
            results.append({
                "source": "youtube",
                "title": snippet.get("title", "YouTube travel video"),
                "description": str(snippet.get("description", ""))[:200],
                "image": _proxify(thumb),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            })
        return results
    except Exception as exc:
        print("ERROR in hidden YouTube search:", exc)
        return []


async def get_hidden_social(location: str, query: str = "", limit: int = 3):
    limit = max(1, min(int(limit or 3), 3))
    search = f"{query.strip()} {location}".strip() if query.strip() else f"hidden peaceful places {location}"
    youtube, reddit = await __import__("asyncio").gather(
        _youtube(search, limit),
        _reddit(search, limit),
    )
    return youtube + reddit
