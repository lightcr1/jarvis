#!/usr/bin/env python3
"""Classify changed paths against config/agent-policy.json."""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "agent-policy.json"


def _git(*args: str) -> list[str]:
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def changed_paths(args: argparse.Namespace) -> list[str]:
    if args.paths:
        return sorted(set(args.paths))
    if args.staged:
        return _git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    if args.base and args.head:
        try:
            return _git("diff", "--name-only", "--diff-filter=ACMR", f"{args.base}...{args.head}")
        except subprocess.CalledProcessError:
            return _git("diff", "--name-only", "--diff-filter=ACMR", args.base, args.head)
    return _git("diff", "--name-only", "--diff-filter=ACMR", "HEAD")


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--base")
    parser.add_argument("--head")
    args = parser.parse_args()

    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    paths = changed_paths(args)
    allowed_examples = policy.get("allow_example_paths", [])
    denied = [p for p in paths if matches(p, policy["deny_paths"]) and not matches(p, allowed_examples)]
    protected = [p for p in paths if matches(p, policy["protected_paths"])]
    ordinary = [p for p in paths if p not in denied and p not in protected]

    print(json.dumps({"denied": denied, "protected": protected, "ordinary": ordinary}, indent=2))
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"requires_human_review={'true' if protected else 'false'}\n")
            handle.write(f"denied_count={len(denied)}\n")
    if denied:
        print("Denied paths must not be committed.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
