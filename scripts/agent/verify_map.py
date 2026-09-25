#!/usr/bin/env python3
"""Map changed repository paths to the pytest files that should cover them.

Heuristic but deterministic: used by ``scripts/agent/verify.sh`` to run only
the affected tests instead of the whole (slow) suite. ``tests_for_paths`` is
pure and unit-tested.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Filenames that are too generic to map to a single test module on their own.
GENERIC_STEMS = {
    "__init__", "store", "service", "client", "models", "permissions",
    "path_safety", "utils", "helpers", "settings", "config",
}


def candidate_names(path: str) -> set[str]:
    """Test-name substrings that likely cover ``path``."""
    parts = Path(path).parts
    if not parts:
        return set()
    names: set[str] = set()
    stem = Path(path).stem
    if parts[0] == "jarvis":
        if len(parts) >= 3 and parts[1] not in ("__pycache__",):
            names.add(parts[1])
        if stem.startswith("api_"):
            stem = stem[4:]
        if stem not in GENERIC_STEMS:
            names.add(stem)
    elif parts[0] == "scripts":
        if "agent" in parts:
            names.update({"autonomy_loop", "agent_policy"})
        elif stem not in GENERIC_STEMS:
            names.add(stem)
    elif stem not in GENERIC_STEMS:
        names.add(stem)
    return {name for name in names if name}


def tests_for_paths(paths: list[str], repo_root: Path) -> list[Path]:
    repo_root = Path(repo_root)
    tests_dir = repo_root / "tests"
    test_files = sorted(tests_dir.glob("test_*.py"))
    matched: set[Path] = set()
    for path in paths:
        if not path or path.startswith("frontend/"):
            continue
        if path.startswith("tests/"):
            candidate = repo_root / path
            if candidate.exists():
                matched.add(candidate)
            continue
        names = candidate_names(path)
        for test_file in test_files:
            if any(name in test_file.stem for name in names):
                matched.add(test_file)
    return sorted(matched)


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    for test_file in tests_for_paths(argv[1:], repo_root):
        print(test_file.relative_to(repo_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
