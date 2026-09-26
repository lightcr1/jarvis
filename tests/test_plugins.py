"""Tests fuer das Plugin-Manifest-Format (Plan 5.2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis.plugins import PluginManifestError, load_plugins, parse_manifest

REGISTRY = {"status.read": {"tier": "T0"}, "service.restart": {"tier": "T2"}}


def _manifest(**over):
    data = {"name": "backup_reporter", "version": "0.1.0", "capabilities": ["status.read"],
            "tier": "T0", "credentials": [], "network_targets": []}
    data.update(over)
    return data


def test_valid_manifest_parses():
    spec = parse_manifest(_manifest(credentials=["backup_api"], network_targets=["10.0.0.5:22"]),
                          REGISTRY)
    assert spec.name == "backup_reporter" and spec.tier == "T0"
    assert spec.capabilities == ("status.read",)
    assert spec.credentials == ("backup_api",) and spec.network_targets == ("10.0.0.5:22",)


@pytest.mark.parametrize("over", [
    {"name": "../evil"}, {"name": "Bad Name"}, {"version": ""}, {"tier": "T9"},
    {"capabilities": []}, {"capabilities": "status.read"}, {"network_targets": "nope"},
])
def test_invalid_manifests_are_rejected(over):
    with pytest.raises(PluginManifestError):
        parse_manifest(_manifest(**over), REGISTRY)


def test_missing_field_is_rejected():
    data = _manifest()
    del data["network_targets"]
    with pytest.raises(PluginManifestError):
        parse_manifest(data, REGISTRY)


def test_plugin_may_not_lower_risk_and_new_caps_are_at_least_t2():
    with pytest.raises(PluginManifestError):
        parse_manifest(_manifest(capabilities=["service.restart"], tier="T1"), REGISTRY)
    with pytest.raises(PluginManifestError):
        parse_manifest(_manifest(capabilities=["brand.new"], tier="T1"), REGISTRY)
    assert parse_manifest(_manifest(capabilities=["brand.new"], tier="T2"), REGISTRY).tier == "T2"


def test_credentials_must_be_references_not_values():
    with pytest.raises(PluginManifestError):
        parse_manifest(_manifest(credentials={"backup_api": "s3cr3t"}), REGISTRY)


def test_load_plugins_reads_and_validates_directory(tmp_path):
    good = tmp_path / "backup_reporter"
    good.mkdir()
    (good / "manifest.json").write_text(json.dumps(_manifest()), encoding="utf-8")
    assert [s.name for s in load_plugins(tmp_path, REGISTRY)] == ["backup_reporter"]

    bad = tmp_path / "broken"
    bad.mkdir()
    (bad / "manifest.json").write_text(json.dumps(_manifest(tier="T9")), encoding="utf-8")
    with pytest.raises(PluginManifestError):
        load_plugins(tmp_path, REGISTRY)


def test_missing_plugins_dir_is_empty(tmp_path):
    assert load_plugins(Path(tmp_path) / "nope", REGISTRY) == []


def test_task_spec_for_missing_capability():
    from jarvis.plugins import task_spec_for_missing_capability

    spec = task_spec_for_missing_capability("baue mir ein Wetter-Plugin", capability="weather.read")
    assert spec["area"] == "build" and spec["size"] == "medium" and spec["source"] == "owner"
    assert "weather.read" in spec["title"] and "Risiko-Vorschlag" in spec["description"]


def _write_plugin(tmp_path, body="LOADED = True\n"):
    plugin = tmp_path / "demo"
    plugin.mkdir()
    (plugin / "manifest.json").write_text(json.dumps(_manifest(name="demo")), encoding="utf-8")
    (plugin / "tool.py").write_text(body, encoding="utf-8")
    return plugin


def test_load_plugin_tools_is_disabled_by_default(tmp_path):
    from jarvis.plugins import load_plugin_tools
    _write_plugin(tmp_path)
    assert load_plugin_tools(tmp_path, REGISTRY, allow_code=False) == []


def test_load_plugin_tools_executes_when_enabled(tmp_path):
    from jarvis.plugins import load_plugin_tools
    plugin = _write_plugin(tmp_path)
    tools = load_plugin_tools(tmp_path, REGISTRY, allow_code=True)
    assert len(tools) == 1
    assert tools[0]["plugin"].name == "demo"
    assert tools[0]["module"].LOADED is True
    assert plugin.is_dir()
