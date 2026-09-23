#!/usr/bin/env python3
"""Typed client for the request-only Jarvis gateway available to OpenHands."""
from __future__ import annotations
import argparse, json, os, sys, urllib.error, urllib.parse, urllib.request

BASE = os.getenv("JARVIS_AGENT_GATEWAY", "http://inference-gateway:8080/jarvis-agent")


def call(method: str, path: str, body: dict | None = None) -> dict:
    token = os.getenv("JARVIS_AGENT_REQUEST_TOKEN", "")
    if not token:
        raise RuntimeError("JARVIS_AGENT_REQUEST_TOKEN is not configured")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
        headers={"X-Jarvis-Agent-Request-Token": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read(65537))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"gateway HTTP {exc.code}: {exc.read(500).decode(errors='replace')}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    idea = sub.add_parser("propose-idea"); idea.add_argument("kind"); idea.add_argument("title"); idea.add_argument("summary"); idea.add_argument("benefit"); idea.add_argument("risks"); idea.add_argument("next_step")
    grant = sub.add_parser("request-grant"); grant.add_argument("kind"); grant.add_argument("target"); grant.add_argument("operation"); grant.add_argument("reason"); grant.add_argument("--duration", type=int, default=3600)
    status = sub.add_parser("grant-status"); status.add_argument("id")
    project = sub.add_parser("request-project"); project.add_argument("kind"); project.add_argument("target"); project.add_argument("title"); project.add_argument("operations", nargs="+"); project.add_argument("--duration", type=int, default=7*24*3600)
    project_status = sub.add_parser("project-status"); project_status.add_argument("id")
    meta = sub.add_parser("repo-metadata"); meta.add_argument("repository")
    pr = sub.add_parser("request-pr"); pr.add_argument("repository"); pr.add_argument("title"); pr.add_argument("body"); pr.add_argument("head"); pr.add_argument("base")
    execute = sub.add_parser("execute-action"); execute.add_argument("id")
    args = parser.parse_args(); values = vars(args); cmd = values.pop("cmd")
    if cmd == "propose-idea": result = call("POST", "/ideas", values)
    elif cmd == "request-grant": result = call("POST", "/grants/requests", {"duration_seconds": values.pop("duration"), **values})
    elif cmd == "grant-status": result = call("GET", f"/grants/requests/{urllib.parse.quote(args.id, safe='')}")
    elif cmd == "request-project": result = call("POST", "/projects", {"duration_seconds": values.pop("duration"), **values})
    elif cmd == "project-status": result = call("GET", f"/projects/{urllib.parse.quote(args.id, safe='')}")
    elif cmd == "repo-metadata":
        owner, repo = args.repository.split("/", 1); result = call("GET", f"/repositories/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(repo, safe='')}/metadata")
    elif cmd == "request-pr": result = call("POST", "/actions/github-pull-request", values)
    else: result = call("POST", f"/actions/{urllib.parse.quote(args.id, safe='')}/execute")
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr); raise SystemExit(1)
