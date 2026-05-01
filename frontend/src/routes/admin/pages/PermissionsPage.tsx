import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AdminGroup,
  AdminPermissionMap,
  AdminUser,
  fetchAdminGroups,
  fetchAdminPermissions,
  fetchAdminUsers,
  fetchEffectivePermissions,
  updateAdminPermissions,
} from "../../../shared/api/admin";
import { useAuth } from "../../../features/auth/AuthProvider";

const HOME_ASSISTANT_PREFIX = "home_assistant.";

const FULL_HA_PERMISSIONS = [
  "home_assistant.access",
  "home_assistant.device_discovery",
  "home_assistant.device_control",
  "home_assistant.security_device_control",
  "home_assistant.system_control",
  "home_assistant.integration_management",
  "home_assistant.remote_control",
  "home_assistant.automation_management",
];

export function PermissionsPage() {
  const { user } = useAuth();
  const [permissions, setPermissions] = useState<AdminPermissionMap | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [groups, setGroups] = useState<AdminGroup[]>([]);
  const [scope, setScope] = useState<"users" | "groups">("users");
  const [target, setTarget] = useState("");
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);
  const [effective, setEffective] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const targetOptions = useMemo(() => (scope === "users" ? users : groups), [groups, scope, users]);
  const homeAssistantPermissions = useMemo(
    () => (permissions?.known_permissions || []).filter((item) => item.startsWith(HOME_ASSISTANT_PREFIX)),
    [permissions],
  );
  const platformPermissions = useMemo(
    () => (permissions?.known_permissions || []).filter((item) => !item.startsWith(HOME_ASSISTANT_PREFIX)),
    [permissions],
  );

  const load = useCallback(async () => {
    const [permissionData, userData, groupData] = await Promise.all([
      fetchAdminPermissions(),
      fetchAdminUsers(),
      fetchAdminGroups(),
    ]);
    setPermissions(permissionData);
    setUsers(userData.users || []);
    setGroups(groupData.groups || []);
  }, []);

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  useEffect(() => {
    if (!permissions || !targetOptions.length) return;
    const preferredTarget = scope === "users" ? user?.id : "";
    const nextTarget = target || preferredTarget || targetOptions[0]?.id || "";
    setTarget(nextTarget);
    const source = scope === "users" ? permissions.user_permissions : permissions.group_permissions;
    setSelectedPermissions(source?.[nextTarget] || []);
    setStatus("");
    setError("");
  }, [permissions, scope, target, targetOptions, user?.id]);

  const currentTarget = targetOptions.find((item) => item.id === target);
  const selectedSet = useMemo(() => new Set(selectedPermissions), [selectedPermissions]);

  function togglePermission(permission: string) {
    setSelectedPermissions((current) => (
      current.includes(permission)
        ? current.filter((item) => item !== permission)
        : [...current, permission].sort()
    ));
  }

  function applyHaPreset(nextHaPermissions: string[]) {
    setSelectedPermissions((current) => {
      const nonHa = current.filter((item) => !item.startsWith(HOME_ASSISTANT_PREFIX));
      return [...nonHa, ...nextHaPermissions].sort();
    });
  }

  async function savePermissions(nextPermissions: string[], successMessage: string) {
    if (!target) return;
    setSaving(true);
    setStatus("");
    setError("");
    try {
      await updateAdminPermissions(scope, target, nextPermissions);
      await load();
      setSelectedPermissions(nextPermissions);
      setStatus(successMessage);
      if (scope === "users") {
        const data = await fetchEffectivePermissions(target);
        setEffective(JSON.stringify(data, null, 2));
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (!permissions) return <div className="panel">Loading permissions…</div>;

  return (
    <div className="page-stack">
      <div className="dashboard-grid">
        <div className="panel metric-card">
          <div className="eyebrow">Known permissions</div>
          <strong>{permissions.known_permissions.length}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">HA permissions</div>
          <strong>{homeAssistantPermissions.length}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">User permission sets</div>
          <strong>{Object.keys(permissions.user_permissions).length}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">Group permission sets</div>
          <strong>{Object.keys(permissions.group_permissions).length}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">Editor scope</div>
          <strong>{scope}</strong>
        </div>
      </div>

      <div className="panel">
        <div className="eyebrow">Permission editor</div>
        <div className="form-row">
          <select className="ui-input" value={scope} onChange={(e) => setScope(e.target.value as "users" | "groups")}>
            <option value="users">User</option>
            <option value="groups">Group</option>
          </select>
          <select
            className="ui-input"
            value={target}
            onChange={(e) => {
              const value = e.target.value;
              setTarget(value);
              const source = scope === "users" ? permissions.user_permissions : permissions.group_permissions;
              setSelectedPermissions(source?.[value] || []);
              setStatus("");
            }}
          >
            {targetOptions.map((item) => (
              <option key={item.id} value={item.id}>{"username" in item ? item.username : item.name}</option>
            ))}
          </select>
        </div>
        <div className="dashboard-stat-list">
          <div><span>Selected target</span><strong>{currentTarget ? ("username" in currentTarget ? currentTarget.username : currentTarget.name) : "none selected"}</strong></div>
          <div><span>Target ID</span><strong>{target || "not set"}</strong></div>
          <div><span>Directly assigned</span><strong>{selectedPermissions.length}</strong></div>
          <div><span>HA permissions</span><strong>{selectedPermissions.filter((item) => item.startsWith(HOME_ASSISTANT_PREFIX)).length}</strong></div>
          <div><span>Platform permissions</span><strong>{selectedPermissions.filter((item) => !item.startsWith(HOME_ASSISTANT_PREFIX)).length}</strong></div>
        </div>
        <div className="page-stack">
          <div className="permission-bundle-card">
            <div className="eyebrow">HA bundle</div>
            <h3>Home Assistant Full Access</h3>
            <p>Grants all Home Assistant permissions in one step. This is the recommended default path.</p>
            <div className="inline-actions">
              <button
                type="button"
                className="ui-button primary"
                disabled={!target || saving}
                onClick={() => {
                  const nonHa = selectedPermissions.filter((item) => !item.startsWith(HOME_ASSISTANT_PREFIX));
                  const nextPermissions = [...nonHa, ...FULL_HA_PERMISSIONS].sort();
                  void savePermissions(nextPermissions, "Home Assistant Full Access saved.");
                }}
              >
                Save Full HA Access
              </button>
              <button type="button" className="ui-button ghost" disabled={saving} onClick={() => applyHaPreset(FULL_HA_PERMISSIONS)}>Preview selection</button>
              <button type="button" className="ui-button ghost" disabled={saving} onClick={() => applyHaPreset([])}>Clear HA permissions</button>
            </div>
          </div>

          <details className="permission-advanced">
            <summary>Advanced individual permissions</summary>
            <div className="page-stack">
              <div>
            <div className="eyebrow">Home Assistant permissions</div>
            <div className="permission-toggle-grid">
              {homeAssistantPermissions.map((item) => (
                <button
                  key={item}
                  type="button"
                  className={`permission-toggle${selectedSet.has(item) ? " active" : ""}`}
                  onClick={() => togglePermission(item)}
                >
                  {item}
                </button>
              ))}
            </div>
              </div>

              <div>
            <div className="eyebrow">Other platform permissions</div>
            <div className="permission-toggle-grid">
              {platformPermissions.map((item) => (
                <button
                  key={item}
                  type="button"
                  className={`permission-toggle${selectedSet.has(item) ? " active" : ""}`}
                  onClick={() => togglePermission(item)}
                >
                  {item}
                </button>
              ))}
            </div>
              </div>
            </div>
          </details>
        </div>
        <div className="inline-actions">
          <button
            className="ui-button primary"
            disabled={!target || saving}
            onClick={() => { void savePermissions(selectedPermissions, "Permissions saved."); }}
          >
            {saving ? "Saving…" : "Save"}
          </button>
          <button
            className="ui-button ghost"
            disabled={!target || saving}
            onClick={async () => {
              if (scope !== "users") return;
              try {
                setError("");
                const data = await fetchEffectivePermissions(target);
                setEffective(JSON.stringify(data, null, 2));
              } catch (err) {
                setError((err as Error).message);
              }
            }}
          >
            Load effective permissions
          </button>
        </div>
        {status ? <div className="tiny-note">{status}</div> : null}
        {error ? <div className="error-text">{error}</div> : null}
      </div>

      <div className="dashboard-grid">
        <div className="panel span-2">
          <div className="eyebrow">Home Assistant permissions</div>
          <div className="permission-grid">
            {homeAssistantPermissions.map((item) => <span className="tag" key={item}>{item}</span>)}
          </div>
          <p className="tiny-note">HA permissions must be explicitly granted. The admin role alone does not imply Home Assistant access or sensitive control rights.</p>
        </div>
        <div className="panel span-2">
          <div className="eyebrow">Other platform permissions</div>
          <div className="permission-grid">
            {platformPermissions.map((item) => <span className="tag" key={item}>{item}</span>)}
          </div>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="panel span-4">
          <div className="eyebrow">Effective / current</div>
          <pre>{effective || "Select a user and load effective permissions."}</pre>
        </div>
      </div>
    </div>
  );
}
