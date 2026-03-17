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

export function PermissionsPage() {
  const [permissions, setPermissions] = useState<AdminPermissionMap | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [groups, setGroups] = useState<AdminGroup[]>([]);
  const [scope, setScope] = useState<"users" | "groups">("users");
  const [target, setTarget] = useState("");
  const [editor, setEditor] = useState("");
  const [effective, setEffective] = useState("");
  const targetOptions = useMemo(() => (scope === "users" ? users : groups), [groups, scope, users]);

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
    const nextTarget = target || targetOptions[0]?.id || "";
    setTarget(nextTarget);
    const source = scope === "users" ? permissions.user_permissions : permissions.group_permissions;
    setEditor((source?.[nextTarget] || []).join("\n"));
  }, [permissions, scope, target, targetOptions]);

  if (!permissions) return <div className="panel">Loading permissions…</div>;

  return (
    <div className="page-stack">
      <div className="dashboard-grid">
        <div className="panel metric-card">
          <div className="eyebrow">Known permissions</div>
          <strong>{permissions.known_permissions.length}</strong>
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
              setEditor((source?.[value] || []).join("\n"));
            }}
          >
            {targetOptions.map((item) => (
              <option key={item.id} value={item.id}>{"username" in item ? item.username : item.name}</option>
            ))}
          </select>
        </div>
        <textarea className="composer-input" value={editor} onChange={(e) => setEditor(e.target.value)} />
        <div className="inline-actions">
          <button
            className="ui-button primary"
            onClick={async () => {
              await updateAdminPermissions(scope, target, editor.split("\n").map((item) => item.trim()).filter(Boolean));
              await load();
            }}
          >
            Save permissions
          </button>
          <button
            className="ui-button ghost"
            onClick={async () => {
              if (scope !== "users") return;
              const data = await fetchEffectivePermissions(target);
              setEffective(JSON.stringify(data, null, 2));
            }}
          >
            Load effective
          </button>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="panel span-2">
          <div className="eyebrow">Known permissions</div>
          <div className="permission-grid">
            {permissions.known_permissions.map((item) => <span className="tag" key={item}>{item}</span>)}
          </div>
        </div>
        <div className="panel span-2">
          <div className="eyebrow">Effective / current</div>
          <pre>{effective || "Select a user and load effective permissions."}</pre>
        </div>
      </div>
    </div>
  );
}
