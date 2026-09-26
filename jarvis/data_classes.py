"""Datenklassen (Plan 2.4): public / personal / sensitive.

`public` darf an Cloud-Modelle, `personal` nur mit ausdruecklichem Einverstaendnis
pro Anfrage, `sensitive` nie. Der selbst gehostete Provider heisst `local` und
bekommt alles. Unbekannte/fehlende Klassen gelten als `personal` (konservativ).
"""
from __future__ import annotations

PUBLIC = "public"
PERSONAL = "personal"
SENSITIVE = "sensitive"
DATA_CLASSES = (PUBLIC, PERSONAL, SENSITIVE)
DEFAULT_DATA_CLASS = PERSONAL


def normalize(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in DATA_CLASSES else DEFAULT_DATA_CLASS


def is_cloud_provider(provider: str | None) -> bool:
    return str(provider or "").strip().lower() != "local"


def allowed_for_cloud(data_class: str | None, *, consent: bool = False) -> bool:
    cls = normalize(data_class)
    if cls == PUBLIC:
        return True
    if cls == PERSONAL:
        return bool(consent)
    return False


def filter_for_provider(items: list[dict], provider: str | None, *, consent: bool = False) -> list[dict]:
    """Behaelt nur Eintraege, die an den gewaehlten Provider duerfen."""
    if not is_cloud_provider(provider):
        return list(items)
    return [item for item in items if allowed_for_cloud((item or {}).get("data_class"), consent=consent)]
