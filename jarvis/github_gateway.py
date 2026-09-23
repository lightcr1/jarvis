"""Small read-only GitHub adapter; never accepts an arbitrary URL or agent token."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request


class GithubGatewayError(ValueError):
    pass


_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def canonical_repo(owner: str, repository: str) -> str:
    if not _OWNER.fullmatch(owner) or not _REPO.fullmatch(repository) or repository in {".", ".."}:
        raise GithubGatewayError("invalid GitHub repository name")
    return f"{owner.lower()}/{repository.lower()}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise GithubGatewayError("redirect blocked")


def public_repository_metadata(owner: str, repository: str) -> dict:
    """Anonymous GitHub API read only: no credentials and no user-controlled host."""
    canonical = canonical_repo(owner, repository)
    req = urllib.request.Request(
        f"https://api.github.com/repos/{canonical}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Jarvis-Scoped-Research"},
        method="GET",
    )
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=8) as response:
            if response.status != 200:
                raise GithubGatewayError("GitHub metadata unavailable")
            raw = response.read(65537)
            if len(raw) > 65536:
                raise GithubGatewayError("GitHub response too large")
            data = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise GithubGatewayError("GitHub metadata unavailable") from exc
    if not isinstance(data, dict) or str(data.get("full_name", "")).lower() != canonical:
        raise GithubGatewayError("unexpected GitHub repository")
    # Return a bounded, untrusted *data* summary, never raw repository instructions.
    return {
        "repository": canonical,
        "description": str(data.get("description") or "")[:300],
        "url": f"https://github.com/{canonical}",
        "default_branch": str(data.get("default_branch") or "")[:100],
        "archived": data.get("archived") is True,
        "stars": max(0, int(data.get("stargazers_count") or 0)),
    }
