"""Plugin-Format: Manifest pruefen, Risiko und Zugriffe begrenzen (Plan 5.2).

Klein anfangen: ein Plugin lebt in ``jarvis/plugins/<name>/`` mit ``manifest.json``
(+ spaeter ``tool.py`` + Tests). Der Loader prueft **nur das Manifest** -- er
fuehrt keinen Plugin-Code aus und liest keine Secrets. Ein Plugin darf sein
Risiko nie unter die Capability-Registry senken, bekommt nur die deklarierten
Credentials-*Referenzen* (keine Werte) und nur die deklarierten Netzziele
(Egress ueber den Allowlist-Proxy).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .capabilities import DEFAULT_TIER, TIERS, load_capabilities, tier_for

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_.]{1,80}$")
REQUIRED_FIELDS = ("name", "version", "capabilities", "tier", "credentials", "network_targets")


class PluginManifestError(ValueError):
    """Ungueltiges Plugin-Manifest."""


@dataclass(frozen=True)
class PluginSpec:
    name: str
    version: str
    tier: str
    capabilities: tuple[str, ...]
    credentials: tuple[str, ...] = field(default=())
    network_targets: tuple[str, ...] = field(default=())
    description: str = ""


def default_plugins_dir() -> Path:
    return Path(__file__).resolve().parent / "plugins"


def _tier_index(tier: str) -> int:
    return TIERS.index(tier) if tier in TIERS else len(TIERS)


def _string_list(value, field_name: str) -> tuple[str, ...]:
    if isinstance(value, dict):
        raise PluginManifestError(
            f"'{field_name}' muss eine Liste von Referenzen sein, keine Werte")
    if not isinstance(value, (list, tuple)):
        raise PluginManifestError(f"'{field_name}' muss eine Liste sein")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise PluginManifestError(f"'{field_name}' darf nur nicht-leere Strings enthalten")
        result.append(item.strip())
    return tuple(result)


def parse_manifest(data: dict, registry: dict[str, dict] | None = None) -> PluginSpec:
    """Prueft ein Manifest und liefert eine PluginSpec (keine Code-Ausfuehrung)."""
    if not isinstance(data, dict):
        raise PluginManifestError("manifest muss ein Objekt sein")
    for key in REQUIRED_FIELDS:
        if key not in data:
            raise PluginManifestError(f"manifest fehlt '{key}'")

    name = str(data["name"]).strip()
    if not NAME_RE.match(name):
        raise PluginManifestError("ungueltiger Plugin-Name (nur a-z, 0-9, _)")
    version = str(data["version"]).strip()
    if not version:
        raise PluginManifestError("version darf nicht leer sein")
    tier = str(data["tier"]).strip().upper()
    if tier not in TIERS:
        raise PluginManifestError(f"ungueltige Risikostufe '{data['tier']}'")

    capabilities = _string_list(data["capabilities"], "capabilities")
    if not capabilities:
        raise PluginManifestError("capabilities darf nicht leer sein")

    active_registry = registry if registry is not None else load_capabilities()
    for capability in capabilities:
        if not CAPABILITY_RE.match(capability):
            raise PluginManifestError(f"ungueltiger Capability-Name '{capability}'")
        registry_tier = tier_for(capability, active_registry)
        if capability not in active_registry:
            registry_tier = DEFAULT_TIER  # neue Capability ist mindestens T2
        if _tier_index(tier) < _tier_index(registry_tier):
            raise PluginManifestError(
                f"Plugin-Stufe {tier} ist schwaecher als {registry_tier} fuer '{capability}'")

    return PluginSpec(
        name=name,
        version=version,
        tier=tier,
        capabilities=capabilities,
        credentials=_string_list(data["credentials"], "credentials"),
        network_targets=_string_list(data["network_targets"], "network_targets"),
        description=str(data.get("description") or "")[:400],
    )


def load_plugins(root: Path | None = None, registry: dict[str, dict] | None = None) -> list[PluginSpec]:
    """Liest und prueft alle ``<root>/*/manifest.json`` (ohne Code auszufuehren)."""
    directory = Path(root) if root is not None else default_plugins_dir()
    specs: list[PluginSpec] = []
    if not directory.is_dir():
        return specs
    for manifest in sorted(directory.glob("*/manifest.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PluginManifestError(f"{manifest}: {exc}") from exc
        specs.append(parse_manifest(data, registry))
    return specs


def task_spec_for_missing_capability(request_text: str, capability: str = "") -> dict:
    """Baut die Spezifikation fuer eine Agent-Aufgabe, wenn eine Faehigkeit fehlt (5.1)."""
    request_text = str(request_text or "").strip()
    title = f"Neue Faehigkeit bauen: {capability or request_text[:80]}".strip()
    description = (
        "Der Besitzer braucht eine Faehigkeit, die es noch nicht gibt.\n"
        f"Anliegen: {request_text}\n"
        f"Capability-Vorschlag: {capability or '<noch zu bestimmen>'}\n\n"
        "Spezifikation:\n- Eingaben:\n- Ausgaben:\n- Risiko-Vorschlag (T0-T3):\n- Tests:\n\n"
        "Umsetzung: Tool in tool_registry_tools.py ODER Plugin "
        "(jarvis/plugins/<name>/ mit manifest.json + tool.py + Tests), Eintrag in "
        "config/capabilities.json als VORSCHLAG. Merge nach dev nur bei gruener CI und "
        "ohne geschuetzte Pfade; die Einstufung macht der Besitzer."
    )
    return {"title": title[:140], "description": description[:4000],
            "area": "build", "size": "medium", "source": "owner"}


def load_plugin_tools(root: Path | None = None, registry: dict[str, dict] | None = None,
                      allow_code: bool | None = None) -> list[dict]:
    """Laedt Plugin-``tool.py`` -- nur wenn ``JARVIS_ALLOW_PLUGIN_CODE=1`` (Default: aus)."""
    import importlib.util
    import os
    if allow_code is None:
        allow_code = os.getenv("JARVIS_ALLOW_PLUGIN_CODE", "0").strip() == "1"
    if not allow_code:
        return []
    directory = Path(root) if root is not None else default_plugins_dir()
    tools: list[dict] = []
    for spec in load_plugins(directory, registry):
        tool_path = directory / spec.name / "tool.py"
        if not tool_path.is_file():
            continue
        module_spec = importlib.util.spec_from_file_location(f"jarvis_plugin_{spec.name}", tool_path)
        if module_spec is None or module_spec.loader is None:
            raise PluginManifestError(f"{tool_path}: nicht ladbar")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        tools.append({"plugin": spec, "module": module})
    return tools
