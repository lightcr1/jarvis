#!/usr/bin/env python3
"""Token budget check for the compact agent context files.

Tokens are estimated as ``len(text) / 4`` (≈ 4 chars per token). The check
fails (exit 1) when a file exceeds its budget, so CI catches context bloat
before it eats the 32k model window.

Usage:
    python3 scripts/agent/context_budget.py [repo_root]
"""
from __future__ import annotations

import sys
from pathlib import Path

# Budgets in estimated tokens.
CONTEXT_LIMIT = 1500
AREA_LIMIT = 600


def token_estimate(text: str) -> int:
    return (len(text) + 3) // 4


def iter_budgeted_files(repo_root: Path):
    """Yield (relative_path, limit) for every agent context file."""
    context = repo_root / "docs" / "agent" / "CONTEXT.md"
    if context.exists():
        yield context, CONTEXT_LIMIT
    areas_dir = repo_root / "docs" / "agent" / "areas"
    if areas_dir.is_dir():
        for area in sorted(areas_dir.glob("*.md")):
            yield area, AREA_LIMIT


def inspect_budget(repo_root: Path) -> list[dict]:
    rows = []
    for path, limit in iter_budgeted_files(repo_root):
        tokens = token_estimate(path.read_text(encoding="utf-8"))
        rows.append({
            "path": str(path.relative_to(repo_root)),
            "tokens": tokens,
            "limit": limit,
            "ok": tokens <= limit,
        })
    return rows


def check_budget(repo_root: Path) -> list[dict]:
    return [row for row in inspect_budget(repo_root) if not row["ok"]]


def main(argv: list[str]) -> int:
    repo_root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[2]
    rows = inspect_budget(repo_root)
    for row in rows:
        status = "OK " if row["ok"] else "OVER"
        print(f"{status} {row['path']}: ~{row['tokens']} Tokens (Limit {row['limit']})")
    violations = [row for row in rows if not row["ok"]]
    if violations:
        print(f"FEHLER: {len(violations)} Datei(en) ueber Budget.", file=sys.stderr)
        return 1
    print(f"OK: {len(rows)} Datei(en) im Budget.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
