"""Live Reddit + YouTube discovery used as evidence for Hidden Places AI."""
import asyncio
import os
from urllib.parse import quote_plus
import httpx
import praw
from dotenv import load_dotenv

load_dotenv()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT") or "voyayaha/1.0"
API_BASE = os.getenv("API_BASE", "https://backend-eqzz.onrender.com").rstrip("/")

_reddit_client = None
if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
    try:
        _reddit_client = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            check_for_async=False,
        )
    except Exception as exc:
        print("Reddit client setup error:", repr(exc))


def _proxify(url):
    return f"{API_BASE}/img?url={quote_plus(url)}" if url else None


def _post_to_dict(post):
    image = None
    try:
        if hasattr(post, "preview"):
            images = post.preview.get("images", [])
            if images:
                image = images[0].get("source", {}).get("url")
        if not image and getattr(post, "thumbnail", "").startswith("http"):
            image = post.thumbnail
    except Exception:
        pass
    return {
        "source": "reddit",
        "title": getattr(post, "title", "Reddit travel post"),
        "description": (getattr(post, "selftext", "") or f"From r/{getattr(post, 'subreddit', 'travel')}")[:500],
        "image": _proxify(image),
        "url": f"https://www.reddit.com{getattr(post, 'permalink', '')}",
    }


async def _reddit(query: str, limit: int):
    results = []
    # Prefer authenticated PRAW, then fall back to Reddit's public JSON search.
    if _reddit_client:
        try:
            posts = await asyncio.to_thread(lambda: list(_reddit_client.subreddit("travel").search(query, limit=limit, sort="new")))
            return [_post_to_dict(p) for p in posts]
        except Exception as exc:
            print("Reddit API error:", repr(exc))

    try:
        url = "https://www.reddit.com/search.json"
        params = {"q": query, "sort": "new", "limit": limit, "restrict_sr": "false"}
        headers = {"User-Agent": REDDIT_USER_AGENT}
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        for child in data.get("data", {}).get("children", []):
            p = child.get("data", {})
            image = p.get("url_overridden_by_dest") if str(p.get("url_overridden_by_dest", "")).startswith("http") else None
            results.append({
                "source": "reddit",
                "title": p.get("title", "Reddit travel post"),
                "description": (p.get("selftext") or f"From r/{p.get('subreddit', 'travel')}")[:500],
                "image": _proxify(image),
                "url": f"https://www.reddit.com{p.get('permalink', '')}",
            })
    except Exception as exc:
        print("Public Reddit search error:", repr(exc))
    return results


async def _youtube(query: str, limit: int):
    if not YOUTUBE_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={"part": "snippet", "type": "video", "maxResults": limit, "q": query, "order": "date", "key": YOUTUBE_API_KEY},
            )
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
                "description": str(snippet.get("description", ""))[:500],
                "image": _proxify(thumb),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "published_at": snippet.get("publishedAt"),
            })
        return results
    except Exception as exc:
        print("YouTube API error:", repr(exc))
        return []


async def get_hidden_social(location: str, query: str = "", limit: int = 6):
    """Fetch current social evidence. Returns up to limit per provider."""
    limit = max(1, min(int(limit or 6), 10))
    search = f"{query.strip()} {location}".strip() if query.strip() else f"hidden places offbeat places travel {location}"
    youtube, reddit = await asyncio.gather(_youtube(search, limit), _reddit(search, limit))
    return youtube + reddit
