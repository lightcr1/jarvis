import os
import tempfile
import unittest

from fastapi.testclient import TestClient

import jarvisappv4
from jarvis.authz import resolve_effective_permissions
from jarvis.group_store import GroupStore
from jarvis.integration_credentials import IntegrationCredentialStore
from jarvis.jarvis_engine import normalize_role
from jarvis.membership_store import MembershipStore
from jarvis.permission_store import KNOWN_PERMISSIONS, PermissionStore
from jarvis.secret_crypto import generate_master_key
from jarvis.user_store import UserStore
from jarvis.workspace.guac_auth import GuacamoleTokenError, decode_json_auth_token, encode_json_auth_token
from jarvis.workspace.service import (
    WorkspaceAccessError,
    WorkspaceConfigError,
    WorkspaceCredentialsMissing,
    WorkspaceService,
    WorkspaceWakeUnavailable,
)
from jarvis.workspace.store import WorkspaceTargetStore
from jarvis.workspace.wol import build_magic_packet, normalize_mac


class _AuditLogProbe:
    def __init__(self):
        self.events = []

    def write(self, event: str, payload: dict):
        self.events.append({"event": event, **payload})


VALID_SECRET_HEX = "00112233445566778899aabbccddeeff"[:32]


class GuacAuthTokenTests(unittest.TestCase):
    def test_round_trip(self):
        payload = {
            "username": "jarvis:u1",
            "expires": 1234567890000,
            "connections": {
                "Office Desktop": {
                    "protocol": "rdp",
                    "parameters": {"hostname": "100.1.2.3", "port": "3389", "username": "lukas", "password": "hunter2"},
                }
            },
        }
        token = encode_json_auth_token(VALID_SECRET_HEX, payload)
        self.assertIsInstance(token, str)
        decoded = decode_json_auth_token(VALID_SECRET_HEX, token)
        self.assertEqual(payload, decoded)

    def test_tampered_token_fails_verification(self):
        token = encode_json_auth_token(VALID_SECRET_HEX, {"username": "", "connections": {}})
        tampered = ("A" if token[0] != "A" else "B") + token[1:]
        with self.assertRaises(GuacamoleTokenError):
            decode_json_auth_token(VALID_SECRET_HEX, tampered)

    def test_wrong_key_fails_verification(self):
        token = encode_json_auth_token(VALID_SECRET_HEX, {"username": "", "connections": {}})
        other_key = "ff" * 16
        with self.assertRaises(GuacamoleTokenError):
            decode_json_auth_token(other_key, token)

    def test_invalid_key_length_rejected(self):
        with self.assertRaises(GuacamoleTokenError):
            encode_json_auth_token("abcd", {"username": "", "connections": {}})

    def test_non_hex_key_rejected(self):
        with self.assertRaises(GuacamoleTokenError):
            encode_json_auth_token("not-hex-zzzzzzzzzzzzzzzzzzzzzzzzz", {"username": "", "connections": {}})


class WolPacketTests(unittest.TestCase):
    def test_build_magic_packet_shape(self):
        packet = build_magic_packet("AA:BB:CC:DD:EE:FF")
        self.assertEqual(102, len(packet))
        self.assertEqual(b"\xff" * 6, packet[:6])
        mac_bytes = bytes.fromhex("AABBCCDDEEFF")
        self.assertEqual(mac_bytes * 16, packet[6:])

    def test_normalize_mac_accepts_dashes_and_lowercase(self):
        self.assertEqual("AA:BB:CC:DD:EE:FF", normalize_mac("aa-bb-cc-dd-ee-ff"))

    def test_invalid_mac_rejected(self):
        with self.assertRaises(ValueError):
            normalize_mac("not-a-mac")


class WorkspaceStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_WORKSPACE_STORE_PATH"] = os.path.join(self.tmpdir.name, "workspace.json")
        self.store = WorkspaceTargetStore()

    def tearDown(self):
        os.environ.pop("JARVIS_WORKSPACE_STORE_PATH", None)
        self.tmpdir.cleanup()

    def test_known_permissions_include_workspace_tuple(self):
        self.assertIn("workspace.read", KNOWN_PERMISSIONS)
        self.assertIn("workspace.write", KNOWN_PERMISSIONS)
        self.assertIn("workspace.connect", KNOWN_PERMISSIONS)

    def test_add_list_get_update_delete(self):
        target = self.store.add_target({"name": "Office PC", "os_type": "windows", "protocol": "rdp", "tailscale_host": "100.1.2.3", "port": 3389})
        self.assertTrue(target["id"].startswith("wt-"))
        self.assertEqual(1, len(self.store.list_targets()))
        self.assertEqual("Office PC", self.store.get_target(target["id"])["name"])
        self.assertIsNone(self.store.get_target("missing"))

        updated = self.store.update_target(target["id"], {"name": "Office PC (renamed)"})
        self.assertEqual("Office PC (renamed)", updated["name"])
        self.assertIsNone(self.store.update_target("missing", {"name": "x"}))

        self.assertTrue(self.store.delete_target(target["id"]))
        self.assertFalse(self.store.delete_target(target["id"]))
        self.assertIsNone(self.store.get_target(target["id"]))

    def test_store_self_heals_on_corrupt_file(self):
        path = os.environ["JARVIS_WORKSPACE_STORE_PATH"]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not valid json")
        store = WorkspaceTargetStore()
        self.assertEqual([], store.list_targets())


class WorkspaceServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_WORKSPACE_STORE_PATH"] = os.path.join(base, "workspace.json")
        os.environ["JARVIS_SECRET_KEY"] = generate_master_key()
        os.environ["JARVIS_INTEGRATION_CREDENTIALS_PATH"] = os.path.join(base, "creds.json")

        self.user_store = UserStore()
        self.group_store = GroupStore()
        self.membership_store = MembershipStore()
        self.permission_store = PermissionStore()
        self.store = WorkspaceTargetStore()
        self.credential_store = IntegrationCredentialStore()
        self.audit_probe = _AuditLogProbe()
        self._guac_url = "https://guac.example.com/guacamole"
        self._guac_secret = VALID_SECRET_HEX
        self.service = WorkspaceService(
            store=self.store,
            credential_store=self.credential_store,
            membership_store=self.membership_store,
            permission_store=self.permission_store,
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=normalize_role,
            audit_log=self.audit_probe,
            guacamole_url_fn=lambda: self._guac_url,
            guacamole_secret_fn=lambda: self._guac_secret,
        )

    def tearDown(self):
        for key in ("JARVIS_EMERGENCY_STOP", "JARVIS_SECRET_KEY", "JARVIS_INTEGRATION_CREDENTIALS_PATH"):
            os.environ.pop(key, None)
        self.tmpdir.cleanup()

    def _rdp_target(self, user_id, role, **overrides):
        payload = {
            "name": "Office Desktop",
            "os_type": "windows",
            "protocol": "rdp",
            "tailscale_host": "100.64.1.2",
            **overrides,
        }
        return self.service.create_target(payload, user_id=user_id, role=role)["target"]

    def test_standard_user_denied_without_permission(self):
        user = self.user_store.create_user("nobody", role="standard_user", enabled=True)
        with self.assertRaises(WorkspaceAccessError):
            self.service.list_targets(user_id=user["id"], role=user["role"])

    def test_admin_bypasses_explicit_grant(self):
        admin = self.user_store.create_user("owner", role="admin", enabled=True)
        target = self._rdp_target(admin["id"], admin["role"])
        self.assertEqual("Office Desktop", target["name"])
        self.assertEqual(3389, target["port"])
        listed = self.service.list_targets(user_id=admin["id"], role=admin["role"])
        self.assertEqual(1, len(listed["targets"]))
        self.assertEqual("workspace_target_created", self.audit_probe.events[-1]["event"])

    def test_group_permissions_unlock_workspace_write(self):
        user = self.user_store.create_user("bob", role="standard_user", enabled=True)
        group = self.group_store.create_group("workspace-ops")
        self.membership_store.add_membership(user["id"], group["id"])
        self.permission_store.set_group_permissions(group["id"], ["workspace.read", "workspace.write"])
        target = self._rdp_target(user["id"], user["role"])
        self.assertEqual("Office Desktop", target["name"])

    def test_default_port_assigned_per_protocol(self):
        admin = self.user_store.create_user("owner2", role="admin", enabled=True)
        rdp = self.service.create_target({"name": "Win", "os_type": "windows", "protocol": "rdp", "tailscale_host": "h"}, user_id=admin["id"], role=admin["role"])["target"]
        vnc = self.service.create_target({"name": "Lin", "os_type": "linux", "protocol": "vnc", "tailscale_host": "h2"}, user_id=admin["id"], role=admin["role"])["target"]
        self.assertEqual(3389, rdp["port"])
        self.assertEqual(5900, vnc["port"])

    def test_invalid_os_type_and_protocol_rejected(self):
        admin = self.user_store.create_user("owner3", role="admin", enabled=True)
        with self.assertRaises(ValueError):
            self.service.create_target({"name": "X", "os_type": "macos", "protocol": "rdp", "tailscale_host": "h"}, user_id=admin["id"], role=admin["role"])
        with self.assertRaises(ValueError):
            self.service.create_target({"name": "X", "os_type": "windows", "protocol": "ssh", "tailscale_host": "h"}, user_id=admin["id"], role=admin["role"])
        with self.assertRaises(ValueError):
            self.service.create_target({"name": "", "os_type": "windows", "protocol": "rdp", "tailscale_host": "h"}, user_id=admin["id"], role=admin["role"])

    def test_emergency_stop_blocks_target_writes(self):
        admin = self.user_store.create_user("owner4", role="admin", enabled=True)
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        try:
            with self.assertRaises(PermissionError):
                self._rdp_target(admin["id"], admin["role"])
        finally:
            os.environ.pop("JARVIS_EMERGENCY_STOP", None)

    def test_delete_target_cascades_credentials(self):
        admin = self.user_store.create_user("owner5", role="admin", enabled=True)
        target = self._rdp_target(admin["id"], admin["role"])
        self.service.set_credentials(target["id"], {"username": "lukas", "password": "hunter2"}, user_id=admin["id"], role=admin["role"])
        status = self.service.credentials_status(target["id"], user_id=admin["id"], role=admin["role"])
        self.assertTrue(status["status"]["configured"])

        self.service.delete_target(target["id"], user_id=admin["id"], role=admin["role"])
        # Credential store entry is gone too — re-creating a target with the same id would find nothing.
        raw = self.credential_store.status("workspace", f"workspace:{target['id']}")
        self.assertFalse(raw["configured"])

    def test_rdp_credentials_require_username(self):
        admin = self.user_store.create_user("owner6", role="admin", enabled=True)
        target = self._rdp_target(admin["id"], admin["role"])
        with self.assertRaises(ValueError):
            self.service.set_credentials(target["id"], {"password": "hunter2"}, user_id=admin["id"], role=admin["role"])

    def test_vnc_credentials_do_not_require_username(self):
        admin = self.user_store.create_user("owner7", role="admin", enabled=True)
        target = self.service.create_target(
            {"name": "Linux Box", "os_type": "linux", "protocol": "vnc", "tailscale_host": "100.64.1.9"},
            user_id=admin["id"], role=admin["role"],
        )["target"]
        result = self.service.set_credentials(target["id"], {"password": "hunter2"}, user_id=admin["id"], role=admin["role"])
        self.assertEqual(["password"], result["credentials"]["field_names"])

    def test_connect_without_credentials_raises(self):
        admin = self.user_store.create_user("owner8", role="admin", enabled=True)
        target = self._rdp_target(admin["id"], admin["role"])
        with self.assertRaises(WorkspaceCredentialsMissing):
            self.service.generate_connection_token(target["id"], user_id=admin["id"], role=admin["role"])

    def test_connect_generates_valid_token_and_url(self):
        admin = self.user_store.create_user("owner9", role="admin", enabled=True)
        target = self._rdp_target(admin["id"], admin["role"])
        self.service.set_credentials(target["id"], {"username": "lukas", "password": "hunter2"}, user_id=admin["id"], role=admin["role"])

        result = self.service.generate_connection_token(target["id"], user_id=admin["id"], role=admin["role"])
        self.assertTrue(result["url"].startswith(self._guac_url))
        self.assertIn("?data=", result["url"])
        self.assertGreater(result["expires_at"], 0)

        decoded = decode_json_auth_token(self._guac_secret, result["token"])
        self.assertIn("Office Desktop", decoded["connections"])
        conn = decoded["connections"]["Office Desktop"]
        self.assertEqual("rdp", conn["protocol"])
        self.assertEqual("100.64.1.2", conn["parameters"]["hostname"])
        self.assertEqual("lukas", conn["parameters"]["username"])
        self.assertEqual("hunter2", conn["parameters"]["password"])
        self.assertEqual("workspace_connect_token_issued", self.audit_probe.events[-1]["event"])

    def test_connect_fails_clearly_when_secret_unset(self):
        admin = self.user_store.create_user("owner10", role="admin", enabled=True)
        target = self._rdp_target(admin["id"], admin["role"])
        self.service.set_credentials(target["id"], {"username": "lukas", "password": "hunter2"}, user_id=admin["id"], role=admin["role"])
        self._guac_secret = None
        with self.assertRaises(WorkspaceConfigError):
            self.service.generate_connection_token(target["id"], user_id=admin["id"], role=admin["role"])

    def test_connect_fails_clearly_when_url_unset(self):
        admin = self.user_store.create_user("owner11", role="admin", enabled=True)
        target = self._rdp_target(admin["id"], admin["role"])
        self.service.set_credentials(target["id"], {"username": "lukas", "password": "hunter2"}, user_id=admin["id"], role=admin["role"])
        self._guac_url = ""
        with self.assertRaises(WorkspaceConfigError):
            self.service.generate_connection_token(target["id"], user_id=admin["id"], role=admin["role"])

    def test_wake_blocked_when_no_relay_configured(self):
        admin = self.user_store.create_user("owner12", role="admin", enabled=True)
        target = self._rdp_target(admin["id"], admin["role"])
        with self.assertRaises(WorkspaceWakeUnavailable):
            self.service.trigger_wake(target["id"], user_id=admin["id"], role=admin["role"])

    def test_wake_blocked_when_relay_set_but_no_mac(self):
        admin = self.user_store.create_user("owner13", role="admin", enabled=True)
        target = self._rdp_target(admin["id"], admin["role"], wol_relay_host="100.64.9.9")
        with self.assertRaises(WorkspaceWakeUnavailable):
            self.service.trigger_wake(target["id"], user_id=admin["id"], role=admin["role"])

    def test_wake_returns_stub_when_relay_and_mac_configured(self):
        admin = self.user_store.create_user("owner14", role="admin", enabled=True)
        target = self._rdp_target(admin["id"], admin["role"], wol_relay_host="100.64.9.9", wol_mac="AA:BB:CC:DD:EE:FF")
        result = self.service.trigger_wake(target["id"], user_id=admin["id"], role=admin["role"])
        self.assertEqual("stub_not_sent", result["status"])
        self.assertEqual("100.64.9.9", result["relay_host"])
        self.assertEqual(204, len(result["magic_packet_hex"]))  # 102 bytes hex-encoded
        self.assertEqual("workspace_wake_attempted", self.audit_probe.events[-1]["event"])

    def test_wake_blocked_by_emergency_stop(self):
        admin = self.user_store.create_user("owner15", role="admin", enabled=True)
        target = self._rdp_target(admin["id"], admin["role"], wol_relay_host="100.64.9.9", wol_mac="AA:BB:CC:DD:EE:FF")
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        try:
            with self.assertRaises(PermissionError):
                self.service.trigger_wake(target["id"], user_id=admin["id"], role=admin["role"])
        finally:
            os.environ.pop("JARVIS_EMERGENCY_STOP", None)

    def test_users_isolated_from_each_others_write_access(self):
        admin = self.user_store.create_user("owner16", role="admin", enabled=True)
        target = self._rdp_target(admin["id"], admin["role"])
        viewer = self.user_store.create_user("viewer", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(viewer["id"], ["workspace.read"])
        with self.assertRaises(WorkspaceAccessError):
            self.service.update_target(target["id"], {"name": "hijacked"}, user_id=viewer["id"], role=viewer["role"])
        with self.assertRaises(WorkspaceAccessError):
            self.service.generate_connection_token(target["id"], user_id=viewer["id"], role=viewer["role"])


class WorkspaceApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(base, "admin_passwords.json")
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(base, "user_preferences.json")
        os.environ["JARVIS_WORKSPACE_STORE_PATH"] = os.path.join(base, "workspace.json")
        os.environ["JARVIS_SECRET_KEY"] = generate_master_key()
        os.environ["JARVIS_INTEGRATION_CREDENTIALS_PATH"] = os.path.join(base, "creds.json")
        os.environ["JARVIS_WORKSPACE_GUACAMOLE_URL"] = "https://guac.example.com/guacamole"
        os.environ["JARVIS_WORKSPACE_JSON_SECRET"] = VALID_SECRET_HEX

        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.user_preferences_store = jarvisappv4.UserPreferencesStore()
        jarvisappv4.workspace_target_store = jarvisappv4.WorkspaceTargetStore()
        jarvisappv4.integration_credential_store = jarvisappv4.IntegrationCredentialStore()
        jarvisappv4.workspace_service = jarvisappv4.WorkspaceService(
            store=jarvisappv4.workspace_target_store,
            credential_store=jarvisappv4.integration_credential_store,
            membership_store=jarvisappv4.membership_store,
            permission_store=jarvisappv4.permission_store,
            resolve_effective_permissions=jarvisappv4.resolve_effective_permissions,
            normalize_role=jarvisappv4.normalize_role,
            audit_log=jarvisappv4.audit_log,
        )
        jarvisappv4._identity_tokens.clear()
        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        for key in ("JARVIS_SECRET_KEY", "JARVIS_INTEGRATION_CREDENTIALS_PATH", "JARVIS_WORKSPACE_GUACAMOLE_URL", "JARVIS_WORKSPACE_JSON_SECRET"):
            os.environ.pop(key, None)
        self.tmpdir.cleanup()

    def _create_user_with_permissions(self, admin_token, admin_id, username, permissions):
        created = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {admin_token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"username": username, "role": "standard_user", "enabled": True, "password": f"{username}-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"permissions": permissions},
        )
        login = self.client.post("/auth/login", json={"username": username, "password": f"{username}-pass"})
        return user_id, login.json()["session_token"]

    def test_full_lifecycle_via_api(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "wsuser", ["workspace.read", "workspace.write", "workspace.connect"]
        )
        headers = {"X-Jarvis-Session": session_token}

        created = self.client.post(
            "/workspace/targets", headers=headers,
            json={"name": "Office Desktop", "os_type": "windows", "protocol": "rdp", "tailscale_host": "100.64.1.2"},
        )
        self.assertEqual(200, created.status_code)
        target = created.json()["target"]
        self.assertEqual(3389, target["port"])

        listed = self.client.get("/workspace/targets", headers=headers)
        self.assertEqual(200, listed.status_code)
        self.assertEqual(1, len(listed.json()["targets"]))

        status_before = self.client.get(f"/workspace/targets/{target['id']}/credentials/status", headers=headers)
        self.assertFalse(status_before.json()["status"]["configured"])

        set_creds = self.client.put(
            f"/workspace/targets/{target['id']}/credentials", headers=headers,
            json={"username": "lukas", "password": "hunter2"},
        )
        self.assertEqual(200, set_creds.status_code)

        connect = self.client.post(f"/workspace/targets/{target['id']}/connect", headers=headers)
        self.assertEqual(200, connect.status_code)
        self.assertIn("?data=", connect.json()["url"])

        wake = self.client.post(f"/workspace/targets/{target['id']}/wake", headers=headers)
        self.assertEqual(409, wake.status_code)

        updated = self.client.patch(f"/workspace/targets/{target['id']}", headers=headers, json={"wol_relay_host": "100.64.9.9", "wol_mac": "AA:BB:CC:DD:EE:FF"})
        self.assertEqual(200, updated.status_code)
        wake_ok = self.client.post(f"/workspace/targets/{target['id']}/wake", headers=headers)
        self.assertEqual(200, wake_ok.status_code)
        self.assertEqual("stub_not_sent", wake_ok.json()["status"])

        deleted = self.client.delete(f"/workspace/targets/{target['id']}", headers=headers)
        self.assertEqual(200, deleted.status_code)
        self.assertTrue(deleted.json()["deleted"])

        after_delete = self.client.get("/workspace/targets", headers=headers)
        self.assertEqual(0, len(after_delete.json()["targets"]))

    def test_permission_denied_returns_403(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "noperm", [])
        denied = self.client.get("/workspace/targets", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(403, denied.status_code)

    def test_connect_without_credentials_returns_409(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "noconn", ["workspace.read", "workspace.write", "workspace.connect"]
        )
        headers = {"X-Jarvis-Session": session_token}
        created = self.client.post(
            "/workspace/targets", headers=headers,
            json={"name": "Linux Box", "os_type": "linux", "protocol": "vnc", "tailscale_host": "100.64.1.9"},
        ).json()["target"]
        response = self.client.post(f"/workspace/targets/{created['id']}/connect", headers=headers)
        self.assertEqual(409, response.status_code)

    def test_connect_returns_503_when_not_configured(self):
        os.environ.pop("JARVIS_WORKSPACE_JSON_SECRET", None)
        jarvisappv4.workspace_service.guacamole_secret_fn = lambda: None
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "unconfigured", ["workspace.read", "workspace.write", "workspace.connect"]
        )
        headers = {"X-Jarvis-Session": session_token}
        created = self.client.post(
            "/workspace/targets", headers=headers,
            json={"name": "Linux Box", "os_type": "linux", "protocol": "vnc", "tailscale_host": "100.64.1.9"},
        ).json()["target"]
        self.client.put(f"/workspace/targets/{created['id']}/credentials", headers=headers, json={"password": "x"})
        response = self.client.post(f"/workspace/targets/{created['id']}/connect", headers=headers)
        self.assertEqual(503, response.status_code)

    def test_update_missing_target_returns_404(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "notfound", ["workspace.read", "workspace.write"]
        )
        missing = self.client.patch("/workspace/targets/does-not-exist", headers={"X-Jarvis-Session": session_token}, json={"name": "x"})
        self.assertEqual(404, missing.status_code)

    def test_create_validation_error_returns_400(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(
            admin["token"], admin["user_id"], "badinput", ["workspace.read", "workspace.write"]
        )
        bad = self.client.post(
            "/workspace/targets", headers={"X-Jarvis-Session": session_token},
            json={"name": "", "os_type": "windows", "protocol": "rdp", "tailscale_host": "h"},
        )
        self.assertEqual(400, bad.status_code)


if __name__ == "__main__":
    unittest.main()
