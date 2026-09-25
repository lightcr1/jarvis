"""Bounded web search through a fixed provider; results are untrusted data.

Two providers are supported, selected by server-side configuration only:
- ``brave`` (default): Brave Search API with a server-side token.
- ``searxng``: a self-hosted SearXNG instance over a fixed internal URL.

The agent can never pass an arbitrary URL or provider: the endpoint picks the
provider from the environment, queries a fixed host, blocks redirects and
bounds query, response size and result count.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class ResearchError(ValueError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ResearchError("search redirect blocked")


def _validate_query(query: str) -> str:
    query = (query or "").strip()
    if not query or len(query) > 300 or any(c in query for c in ("\0", "\r", "\n")):
        raise ResearchError("bounded search query required")
    return query


def _bounded_limit(limit: int) -> int:
    return max(1, min(int(limit), 10))


def _bounded_results(items, limit: int) -> list[dict]:
    output = []
    for item in (items or [])[:limit]:
        if not isinstance(item, dict):
            continue
        output.append({
            "title": str(item.get("title") or "")[:200],
            "url": str(item.get("url") or "")[:500],
            "description": str(item.get("description") or item.get("content") or "")[:500],
        })
    return output


def search_web(query: str, token: str, *, limit: int = 5) -> list[dict]:
    """Brave Search API (fixed host)."""
    query = _validate_query(query)
    if not token:
        raise ResearchError("search provider token unavailable")
    limit = _bounded_limit(limit)
    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode(
        {"q": query, "count": limit})
    req = urllib.request.Request(url, headers={"Accept": "application/json", "X-Subscription-Token": token,
                                               "User-Agent": "Jarvis-Scoped-Research"})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=10) as response:
            raw = response.read(262145)
            if response.status != 200 or len(raw) > 262144:
                raise ResearchError("search response rejected")
            data = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise ResearchError("search provider unavailable") from exc
    return _bounded_results((data.get("web") or {}).get("results"), limit)


def search_searxng(query: str, base_url: str, *, limit: int = 5) -> list[dict]:
    """Self-hosted SearXNG JSON API over a fixed internal URL (5.1/search)."""
    query = _validate_query(query)
    base = (base_url or "").strip().rstrip("/")
    if not base or not base.startswith(("http://", "https://")):
        raise ResearchError("searxng url unavailable")
    limit = _bounded_limit(limit)
    url = base + "/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "safesearch": "1", "language": "de-DE"})
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "Jarvis-Scoped-Research"})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=12) as response:
            raw = response.read(524289)
            if response.status != 200 or len(raw) > 524288:
                raise ResearchError("search response rejected")
            data = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise ResearchError("search provider unavailable") from exc
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ResearchError("search response rejected")
    return _bounded_results(data.get("results"), limit)
