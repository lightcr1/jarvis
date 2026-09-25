"""Small read-only GitHub adapter; never accepts an arbitrary URL or agent token."""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
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


def validate_pull_request(payload: dict) -> None:
    if set(payload) != {"title", "body", "head", "base"}:
        raise GithubGatewayError("exact pull request fields required")
    limits = {"title": 200, "body": 10000, "head": 200, "base": 200}
    for key, limit in limits.items():
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > limit or any(c in value for c in ("\0", "\r")):
            raise GithubGatewayError(f"invalid pull request {key}")
    for key in ("head", "base"):
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", payload[key]) or ".." in payload[key] or payload[key].startswith("/"):
            raise GithubGatewayError(f"invalid pull request {key}")


def validate_agent_branch(branch: str) -> None:
    if not re.fullmatch(r"agent/[A-Za-z0-9._/-]{1,180}", branch) or ".." in branch:
        raise GithubGatewayError("agent branch required")


def create_agent_branch(owner: str, repository: str, *, branch: str, base: str, token: str) -> dict:
    canonical = canonical_repo(owner, repository); validate_agent_branch(branch)
    if base not in {"dev", "main"}: raise GithubGatewayError("base branch must be dev or main")
    if not token: raise GithubGatewayError("GitHub write token unavailable")
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
               "User-Agent": "Jarvis-Scoped-Action", "Content-Type": "application/json"}
    try:
        ref_url = f"https://api.github.com/repos/{canonical}/git/ref/heads/{urllib.parse.quote(base, safe='')}"
        with urllib.request.build_opener(_NoRedirect()).open(urllib.request.Request(ref_url, headers=headers), timeout=8) as response:
            sha = json.loads(response.read(65537))["object"]["sha"]
        create_url = f"https://api.github.com/repos/{canonical}/git/refs"
        request = urllib.request.Request(create_url, data=json.dumps({"ref": f"refs/heads/{branch}", "sha": sha}).encode(), headers=headers, method="POST")
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=8) as response:
            if response.status != 201: raise GithubGatewayError("GitHub branch creation failed")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, KeyError, json.JSONDecodeError) as exc:
        raise GithubGatewayError("GitHub branch creation failed") from exc
    return {"repository": canonical, "branch": branch, "base": base, "sha": str(sha)}


def validate_branch_file(path: str, branch: str, content: str, message: str) -> None:
    validate_agent_branch(branch)
    if not path or path.startswith("/") or ".." in path.split("/") or len(path) > 300 or "\\" in path:
        raise GithubGatewayError("safe repository-relative path required")
    lowered = path.lower()
    if (path == "AGENTS.md" or lowered.startswith(".github/") or lowered.startswith("deploy/") or
            any(part.startswith(".env") or "credential" in part or "secret" in part for part in lowered.split("/"))):
        raise GithubGatewayError("protected path cannot be changed through agent gateway")
    if not isinstance(content, str) or len(content.encode()) > 256 * 1024:
        raise GithubGatewayError("file content too large")
    if not message.strip() or len(message) > 200:
        raise GithubGatewayError("bounded commit message required")


def write_branch_file(owner: str, repository: str, *, path: str, branch: str,
                      content: str, message: str, token: str) -> dict:
    canonical = canonical_repo(owner, repository); validate_branch_file(path, branch, content, message)
    if not token: raise GithubGatewayError("GitHub write token unavailable")
    quoted_path = urllib.parse.quote(path, safe="/")
    url = f"https://api.github.com/repos/{canonical}/contents/{quoted_path}"
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
               "User-Agent": "Jarvis-Scoped-Action", "Content-Type": "application/json"}
    sha = None
    try:
        get = urllib.request.Request(url + "?ref=" + urllib.parse.quote(branch, safe=""), headers=headers)
        with urllib.request.build_opener(_NoRedirect()).open(get, timeout=8) as response:
            existing = json.loads(response.read(65537)); sha = existing.get("sha")
    except urllib.error.HTTPError as exc:
        if exc.code != 404: raise GithubGatewayError("GitHub file lookup failed") from exc
    payload = {"message": message, "content": base64.b64encode(content.encode()).decode(), "branch": branch}
    if sha: payload["sha"] = sha
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="PUT")
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=10) as response:
            result = json.loads(response.read(65537))
            if response.status not in (200, 201): raise GithubGatewayError("GitHub file write failed")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise GithubGatewayError("GitHub file write failed") from exc
    return {"repository": canonical, "path": path, "branch": branch,
            "commit": str((result.get("commit") or {}).get("sha") or "")}


def create_pull_request(owner: str, repository: str, payload: dict, token: str) -> dict:
    canonical = canonical_repo(owner, repository)
    validate_pull_request(payload)
    if not token:
        raise GithubGatewayError("GitHub write token unavailable")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{canonical}/pulls",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
                 "User-Agent": "Jarvis-Scoped-Action", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=8) as response:
            raw = response.read(65537)
            if response.status != 201 or len(raw) > 65536:
                raise GithubGatewayError("GitHub pull request creation failed")
            data = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise GithubGatewayError("GitHub pull request creation failed") from exc
    return {"number": int(data["number"]), "url": str(data["html_url"]), "repository": canonical}


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


# ---------------------------------------------------------------------------
# 4.1 Atomic patch submission
# ---------------------------------------------------------------------------

import fnmatch
from pathlib import Path

PATCH_MAX_BYTES = 1024 * 1024


def default_policy_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "agent-policy.json"


def _matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _parse_hunk_header(line: str):
    match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
    if not match:
        return None
    return {
        "old_start": int(match.group(1)),
        "old_count": int(match.group(2) or 1),
        "new_start": int(match.group(3)),
        "new_count": int(match.group(4) or 1),
        "lines": [],
    }


def parse_patch(patch_text: str) -> list[dict]:
    """Parse a git unified diff into per-file hunks (paths only, no execution)."""
    files: list[dict] = []
    current: dict | None = None
    hunk: dict | None = None
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            if current and current.get("path"):
                files.append(current)
            current = {"path": None, "old_path": None, "hunks": [], "new": False, "delete": False}
            hunk = None
        elif current is None:
            continue
        elif line.startswith("new file mode"):
            current["new"] = True
        elif line.startswith("deleted file mode"):
            current["delete"] = True
        elif line.startswith("--- "):
            target = line[4:].strip()
            current["old_path"] = None if target == "/dev/null" else (
                target[2:] if target.startswith("a/") else target)
        elif line.startswith("+++ "):
            target = line[4:].strip()
            current["path"] = None if target == "/dev/null" else (
                target[2:] if target.startswith("b/") else target)
        elif line.startswith("@@"):
            hunk = _parse_hunk_header(line)
            if hunk is not None:
                current["hunks"].append(hunk)
        elif hunk is not None and line[:1] in ("+", "-", " ", "\\"):
            hunk["lines"].append(line)
    if current and current.get("path"):
        files.append(current)
    return files


def apply_unified_diff(old_text: str, hunks: list[dict]) -> str:
    old_lines = old_text.split("\n") if old_text else []
    result: list[str] = []
    old_index = 0
    for hunk in hunks:
        start = max(0, hunk["old_start"] - 1)
        while old_index < start and old_index < len(old_lines):
            result.append(old_lines[old_index])
            old_index += 1
        for line in hunk["lines"]:
            marker = line[:1]
            if marker == "\\":
                continue
            if marker == "+":
                result.append(line[1:])
            elif marker == "-":
                old_index += 1
            elif marker == " ":
                result.append(line[1:])
                old_index += 1
    while old_index < len(old_lines):
        result.append(old_lines[old_index])
        old_index += 1
    return "\n".join(result)


def validate_patch(patch_text: str, *, branch: str, policy: dict | None = None) -> list[str]:
    """Validate a patch (branch, size, no binaries, deny/protected paths)."""
    validate_agent_branch(branch)
    if not isinstance(patch_text, str) or not patch_text.strip():
        raise GithubGatewayError("patch required")
    if len(patch_text.encode()) > PATCH_MAX_BYTES:
        raise GithubGatewayError("patch too large")
    if "GIT binary patch" in patch_text or re.search(r"^Binary files ", patch_text, re.M):
        raise GithubGatewayError("binary patches are not supported")
    files = parse_patch(patch_text)
    if not files:
        raise GithubGatewayError("patch contains no file changes")

    policy = policy if policy is not None else json.loads(default_policy_path().read_text(encoding="utf-8"))
    deny = list(policy.get("deny_paths", []))
    protected = list(policy.get("protected_paths", []))
    allowed_examples = list(policy.get("allow_example_paths", []))

    paths: list[str] = []
    for entry in files:
        path = entry["path"]
        if not path or path.startswith("/") or ".." in path.split("/") or "\\" in path or len(path) > 300:
            raise GithubGatewayError("safe repository-relative path required")
        if _matches(path, deny) and not _matches(path, allowed_examples):
            raise GithubGatewayError(f"denied path in patch: {path}")
        if _matches(path, protected):
            raise GithubGatewayError(f"protected path in patch: {path}")
        paths.append(path)
    return paths


def _gh_json(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
               "User-Agent": "Jarvis-Scoped-Action", "Content-Type": "application/json"}
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=15) as response:
            raw = response.read()
            if len(raw) > 4 * 1024 * 1024:
                raise GithubGatewayError("GitHub response too large")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise FileNotFoundError(url) from exc
        raise GithubGatewayError(f"GitHub API {exc.code}") from exc
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise GithubGatewayError("GitHub API unavailable") from exc


def submit_patch(owner: str, repository: str, *, branch: str, base: str, patch_text: str,
                 message: str, token: str) -> dict:
    """Apply a patch on top of ``base`` and create exactly one commit + ref.

    All repository access goes through the fixed GitHub API host; the patch is
    validated against the agent policy before any write.
    """
    canonical = canonical_repo(owner, repository)
    paths = validate_patch(patch_text, branch=branch)
    if base not in {"dev", "main"}:
        raise GithubGatewayError("base branch must be dev or main")
    if not token:
        raise GithubGatewayError("GitHub write token unavailable")
    if not message.strip() or len(message) > 200 or any(c in message for c in ("\0", "\r")):
        raise GithubGatewayError("bounded commit message required")

    ref = _gh_json("GET", f"https://api.github.com/repos/{canonical}/git/ref/heads/{base}", token)
    base_sha = ref["object"]["sha"]
    base_commit = _gh_json("GET", f"https://api.github.com/repos/{canonical}/git/commits/{base_sha}", token)
    base_tree = base_commit["tree"]["sha"]

    files = parse_patch(patch_text)
    tree_entries = []
    for entry in files:
        path = entry["path"]
        if entry["delete"]:
            tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
            continue
        old_text = ""
        if not entry["new"]:
            quoted = urllib.parse.quote(path, safe="/")
            try:
                content = _gh_json("GET", f"https://api.github.com/repos/{canonical}/contents/{quoted}?ref={base}", token)
                old_text = base64.b64decode(content.get("content", "")).decode("utf-8")
            except FileNotFoundError:
                entry["new"] = True
        new_text = apply_unified_diff(old_text, entry["hunks"])
        blob = _gh_json("POST", f"https://api.github.com/repos/{canonical}/git/blobs", token,
                        {"content": base64.b64encode(new_text.encode()).decode(), "encoding": "base64"})
        tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})

    tree = _gh_json("POST", f"https://api.github.com/repos/{canonical}/git/trees", token,
                    {"base_tree": base_tree, "tree": tree_entries})
    commit = _gh_json("POST", f"https://api.github.com/repos/{canonical}/git/commits", token,
                      {"message": message, "tree": tree["sha"], "parents": [base_sha]})
    _gh_json("PATCH", f"https://api.github.com/repos/{canonical}/git/refs/heads/{branch}", token,
             {"sha": commit["sha"], "force": False})
    return {"repository": canonical, "branch": branch, "base": base,
            "commit": commit["sha"], "paths": paths, "commit_count": 1}
