from __future__ import annotations

from pathlib import Path

MAX_NAME_LENGTH = 255
_FORBIDDEN_CHARS = ("/", "\\", "\x00")


class PathSafetyError(ValueError):
    pass


def sanitize_segment(name: str | None) -> str:
    if name is None:
        raise PathSafetyError("name required")
    candidate = str(name)
    if "\x00" in candidate:
        raise PathSafetyError("name contains a null byte")
    stripped = candidate.strip()
    if not stripped:
        raise PathSafetyError("name required")
    if len(stripped) > MAX_NAME_LENGTH:
        raise PathSafetyError("name too long")
    if any(ch in _FORBIDDEN_CHARS for ch in stripped):
        raise PathSafetyError("name must not contain path separators")
    if stripped in {".", ".."}:
        raise PathSafetyError("invalid name")
    if any(ord(ch) < 0x20 for ch in stripped):
        raise PathSafetyError("name contains control characters")
    return stripped


def resolve_within_root(root: Path, *segments: str) -> Path:
    root_resolved = root.resolve()
    candidate = root_resolved
    for segment in segments:
        safe = sanitize_segment(segment)
        candidate = candidate / safe
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PathSafetyError("resolved path escapes the storage root") from exc
    if resolved == root_resolved and segments:
        raise PathSafetyError("resolved path escapes the storage root")
    return resolved
