"""Bounded web search through a fixed provider; results are untrusted data."""
from __future__ import annotations
import json, urllib.error, urllib.parse, urllib.request

class ResearchError(ValueError): pass

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ResearchError("search redirect blocked")

def search_web(query: str, token: str, *, limit: int = 5) -> list[dict]:
    query = query.strip()
    if not token: raise ResearchError("search provider token unavailable")
    if not query or len(query) > 300 or any(c in query for c in ("\0", "\r", "\n")):
        raise ResearchError("bounded search query required")
    limit = max(1, min(int(limit), 10))
    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": query, "count": limit})
    req = urllib.request.Request(url, headers={"Accept": "application/json", "X-Subscription-Token": token,
                                               "User-Agent": "Jarvis-Scoped-Research"})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=10) as response:
            raw = response.read(262145)
            if response.status != 200 or len(raw) > 262144: raise ResearchError("search response rejected")
            data = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise ResearchError("search provider unavailable") from exc
    output = []
    for item in ((data.get("web") or {}).get("results") or [])[:limit]:
        if isinstance(item, dict):
            output.append({"title": str(item.get("title") or "")[:200], "url": str(item.get("url") or "")[:500],
                           "description": str(item.get("description") or "")[:500]})
    return output
