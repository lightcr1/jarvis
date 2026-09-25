"""Tests fuer den Anliegen-Router (Abschnitt 2.1)."""
from __future__ import annotations

from jarvis.request_router import route_request


def test_existing_tool_is_immediate():
    assert route_request("starte den Dienst neu", has_tool=True)["route"] == "answer"


def test_infra_actions_go_to_executor():
    assert route_request("starte die VM neu")["route"] == "infra"
    assert route_request("mach einen snapshot von proxmox")["route"] == "infra"


def test_build_when_capability_missing():
    assert route_request("baue mir ein Plugin fuer X")["route"] == "build"


def test_task_for_multistep_work():
    assert route_request("recherchiere den Markt und berichte")["route"] == "task"
    assert route_request("x" * 300)["route"] == "task"


def test_simple_question_is_answer():
    assert route_request("Wie ist das Wetter?")["route"] == "answer"
    assert route_request("")["route"] == "answer"
