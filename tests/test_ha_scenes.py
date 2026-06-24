from __future__ import annotations

import os
import tempfile
import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from jarvis.api_home_assistant import build_home_assistant_router
from jarvis.authz import resolve_effective_permissions
from jarvis.group_store import GroupStore
from jarvis.home_assistant.client import HomeAssistantClient
from jarvis.home_assistant.service import HomeAssistantService
from jarvis.home_assistant.store import HomeAssistantStore
from jarvis.membership_store import MembershipStore
from jarvis.permission_store import PermissionStore
from jarvis.user_store import UserStore


class _AuditProbe:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: str, payload: dict) -> None:
        self.events.append({"event": event, **payload})


def _make_service(tmpdir: str) -> tuple[HomeAssistantService, str]:
    os.environ["JARVIS_USER_STORE_PATH"] = f"{tmpdir}/users.json"
    os.environ["JARVIS_GROUP_STORE_PATH"] = f"{tmpdir}/groups.json"
    os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = f"{tmpdir}/memberships.json"
    os.environ["JARVIS_PERMISSION_STORE_PATH"] = f"{tmpdir}/permissions.json"
    os.environ["JARVIS_HOME_ASSISTANT_STORE_PATH"] = f"{tmpdir}/home_assistant.json"
    for key in (
        "JARVIS_HOME_ASSISTANT_CALENDAR_FILE",
        "JARVIS_HOME_ASSISTANT_INBOX_FILE",
        "JARVIS_HOME_ASSISTANT_CALENDAR_URL",
        "JARVIS_HOME_ASSISTANT_CALENDAR_TOKEN",
        "JARVIS_HOME_ASSISTANT_CALENDAR_WRITE_URL",
        "JARVIS_HOME_ASSISTANT_CALENDAR_WRITE_TOKEN",
        "JARVIS_HOME_ASSISTANT_CALENDAR_SEED",
        "JARVIS_HOME_ASSISTANT_INBOX_URL",
        "JARVIS_HOME_ASSISTANT_INBOX_TOKEN",
        "JARVIS_HOME_ASSISTANT_INBOX_WRITE_URL",
        "JARVIS_HOME_ASSISTANT_INBOX_WRITE_TOKEN",
        "JARVIS_HOME_ASSISTANT_INBOX_SEED",
        "JARVIS_HOME_ASSISTANT_REMOTE_ALLOWED_CIDRS",
        "JARVIS_EMERGENCY_STOP",
    ):
        os.environ.pop(key, None)

    user_store = UserStore()
    group_store = GroupStore()
    membership_store = MembershipStore()
    permission_store = PermissionStore()
    store = HomeAssistantStore()
    client = HomeAssistantClient()
    audit = _AuditProbe()
    service = HomeAssistantService(
        store=store,
        client=client,
        user_store=user_store,
        membership_store=membership_store,
        permission_store=permission_store,
        resolve_effective_permissions=resolve_effective_permissions,
        normalize_role=lambda r: r or "guest_restricted",
        audit_log=audit,
    )
    admin = user_store.create_user("owner", role="admin", enabled=True)
    return service, admin["id"]


def _add_entity(service: HomeAssistantService, *, entity_id: str, label: str, kind: str, area: str = "") -> dict:
    return service.store.add_managed_entity(
        {
            "entity_id": entity_id,
            "label": label,
            "kind": kind,
            "area": area,
            "approval_status": "approved",
            "onboarding_status": "managed",
            "available": True,
            "state": "off",
            "metadata": {},
        }
    )


def _build_client(service: HomeAssistantService, admin_id: str, session_token: str = "tok-admin") -> TestClient:
    def require_identity_session(token: str) -> dict:
        if token == session_token:
            return {"token": token, "user": {"id": admin_id, "role": "admin"}}
        raise HTTPException(401, "login required")

    app = FastAPI()
    app.include_router(
        build_home_assistant_router(
            {
                "require_identity_session": require_identity_session,
                "home_assistant_service": service,
            }
        )
    )
    return TestClient(app, raise_server_exceptions=False)


class HAScenesListTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.service, self.admin_id = _make_service(self._tmpdir)

    def test_list_scenes_returns_only_scene_entities(self) -> None:
        _add_entity(self.service, entity_id="scene.evening", label="Evening", kind="scene")
        _add_entity(self.service, entity_id="scene.morning", label="Morning", kind="scene")
        _add_entity(self.service, entity_id="light.kitchen", label="Kitchen Light", kind="light")

        client = _build_client(self.service, self.admin_id)
        resp = client.get("/home-assistant/scenes", headers={"x-jarvis-session": "tok-admin"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("scenes", data)
        ids = [s["entity_id"] for s in data["scenes"]]
        self.assertIn("scene.evening", ids)
        self.assertIn("scene.morning", ids)
        self.assertNotIn("light.kitchen", ids)
        self.assertEqual(len(data["scenes"]), 2)

    def test_list_scenes_empty_when_no_scene_entities(self) -> None:
        _add_entity(self.service, entity_id="light.living", label="Living Light", kind="light")

        client = _build_client(self.service, self.admin_id)
        resp = client.get("/home-assistant/scenes", headers={"x-jarvis-session": "tok-admin"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["scenes"], [])

    def test_list_scenes_scene_shape(self) -> None:
        _add_entity(self.service, entity_id="scene.movie", label="Movie Night", kind="scene")

        client = _build_client(self.service, self.admin_id)
        resp = client.get("/home-assistant/scenes", headers={"x-jarvis-session": "tok-admin"})
        self.assertEqual(resp.status_code, 200)
        scene = resp.json()["scenes"][0]
        self.assertEqual(scene["id"], "scene.movie")
        self.assertEqual(scene["entity_id"], "scene.movie")
        self.assertEqual(scene["name"], "Movie Night")

    def test_list_scenes_401_when_not_authenticated(self) -> None:
        client = _build_client(self.service, self.admin_id)
        resp = client.get("/home-assistant/scenes", headers={"x-jarvis-session": "bad-token"})
        self.assertEqual(resp.status_code, 401)


class HAScenesActivateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.service, self.admin_id = _make_service(self._tmpdir)

    def test_activate_scene_success(self) -> None:
        _add_entity(self.service, entity_id="scene.relax", label="Relax", kind="scene")

        client = _build_client(self.service, self.admin_id)
        resp = client.post("/home-assistant/scenes/scene.relax/activate", headers={"x-jarvis-session": "tok-admin"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["scene_id"], "scene.relax")

    def test_activate_scene_audit_logged(self) -> None:
        _add_entity(self.service, entity_id="scene.dinner", label="Dinner", kind="scene")

        client = _build_client(self.service, self.admin_id)
        client.post("/home-assistant/scenes/scene.dinner/activate", headers={"x-jarvis-session": "tok-admin"})

        audit_events = [e["event"] for e in self.service.audit_log.events]
        self.assertIn("ha_scene_activated", audit_events)

    def test_activate_scene_404_when_entity_not_found(self) -> None:
        client = _build_client(self.service, self.admin_id)
        resp = client.post("/home-assistant/scenes/scene.nonexistent/activate", headers={"x-jarvis-session": "tok-admin"})
        self.assertEqual(resp.status_code, 404)

    def test_activate_scene_404_when_entity_is_not_a_scene(self) -> None:
        _add_entity(self.service, entity_id="light.office", label="Office Light", kind="light")

        client = _build_client(self.service, self.admin_id)
        resp = client.post("/home-assistant/scenes/light.office/activate", headers={"x-jarvis-session": "tok-admin"})
        self.assertEqual(resp.status_code, 404)

    def test_activate_scene_401_when_not_authenticated(self) -> None:
        _add_entity(self.service, entity_id="scene.cozy", label="Cozy", kind="scene")

        client = _build_client(self.service, self.admin_id)
        resp = client.post("/home-assistant/scenes/scene.cozy/activate", headers={"x-jarvis-session": "bad-token"})
        self.assertEqual(resp.status_code, 401)

    def test_activate_scene_blocked_when_emergency_stop_enabled(self) -> None:
        _add_entity(self.service, entity_id="scene.party", label="Party", kind="scene")
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        try:
            client = _build_client(self.service, self.admin_id)
            resp = client.post("/home-assistant/scenes/scene.party/activate", headers={"x-jarvis-session": "tok-admin"})
            self.assertEqual(resp.status_code, 403)
        finally:
            os.environ.pop("JARVIS_EMERGENCY_STOP", None)

    def test_activate_scene_403_when_no_ha_access(self) -> None:
        import tempfile as _tempfile

        tmpdir2 = _tempfile.mkdtemp()
        os.environ["JARVIS_USER_STORE_PATH"] = f"{tmpdir2}/users.json"
        os.environ["JARVIS_HOME_ASSISTANT_STORE_PATH"] = f"{tmpdir2}/ha.json"
        os.environ.pop("JARVIS_EMERGENCY_STOP", None)

        from jarvis.home_assistant.store import HomeAssistantStore as _Store
        from jarvis.user_store import UserStore as _UStore
        from jarvis.membership_store import MembershipStore as _MS
        from jarvis.permission_store import PermissionStore as _PS

        user_store2 = _UStore()
        restricted = user_store2.create_user("restricted", role="guest_restricted", enabled=True)
        service2 = HomeAssistantService(
            store=_Store(),
            client=HomeAssistantClient(),
            user_store=user_store2,
            membership_store=_MS(),
            permission_store=_PS(),
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=lambda r: r or "guest_restricted",
            audit_log=_AuditProbe(),
        )
        service2.store.add_managed_entity(
            {"entity_id": "scene.test", "label": "Test", "kind": "scene", "area": "", "approval_status": "approved", "onboarding_status": "managed", "available": True, "state": "off", "metadata": {}}
        )

        def require_restricted(token: str) -> dict:
            if token == "tok-restricted":
                return {"token": token, "user": {"id": restricted["id"], "role": "guest_restricted"}}
            raise HTTPException(401, "login required")

        app2 = FastAPI()
        app2.include_router(
            build_home_assistant_router(
                {"require_identity_session": require_restricted, "home_assistant_service": service2}
            )
        )
        client2 = TestClient(app2, raise_server_exceptions=False)
        resp = client2.post("/home-assistant/scenes/scene.test/activate", headers={"x-jarvis-session": "tok-restricted"})
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
