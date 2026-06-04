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
import { useJ } from "../../../screens/jarvis-shared";

const HA_PREFIX = "home_assistant.";

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

function labelFor(p: string): string {
  return p.replace(HA_PREFIX, "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function initials(name: string): string {
  return name.slice(0, 2).toUpperCase();
}

export function PermissionsPage() {
  const J = useJ();
  const { user } = useAuth();

  const [permissions, setPermissions] = useState<AdminPermissionMap | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [groups, setGroups] = useState<AdminGroup[]>([]);
  const [scope, setScope] = useState<"users" | "groups">("users");
  const [target, setTarget] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [effective, setEffective] = useState<Record<string, unknown> | null>(null);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [pd, ud, gd] = await Promise.all([
      fetchAdminPermissions(),
      fetchAdminUsers(),
      fetchAdminGroups(),
    ]);
    setPermissions(pd);
    setUsers(ud.users || []);
    setGroups(gd.groups || []);
  }, []);

  useEffect(() => { load().catch(() => undefined); }, [load]);
  useEffect(() => {
    if (!status) return;
    const id = setTimeout(() => setStatus(""), 4000);
    return () => clearTimeout(id);
  }, [status]);

  const targetOptions = scope === "users" ? users : groups;

  useEffect(() => {
    if (!permissions || !targetOptions.length) return;
    const validIds = new Set(targetOptions.map(t => t.id));
    if (validIds.has(target)) {
      const src = scope === "users" ? permissions.user_permissions : permissions.group_permissions;
      setSelected(src?.[target] || []);
    } else {
      const preferred = scope === "users" ? user?.id : "";
      const next = (preferred && validIds.has(preferred) ? preferred : targetOptions[0]?.id) || "";
      setTarget(next);
      setStatus("");
      setError("");
      setEffective(null);
      const src = scope === "users" ? permissions.user_permissions : permissions.group_permissions;
      setSelected(src?.[next] || []);
    }
  }, [permissions, scope, target, targetOptions, user?.id]);

  const haPerms = useMemo(() => (permissions?.known_permissions || []).filter(p => p.startsWith(HA_PREFIX)), [permissions]);
  const platformPerms = useMemo(() => (permissions?.known_permissions || []).filter(p => !p.startsWith(HA_PREFIX)), [permissions]);
  const selectedSet = useMemo(() => new Set(selected), [selected]);

  const filteredTargets = useMemo(() => {
    const q = search.toLowerCase();
    return targetOptions.filter(t => {
      const name = "username" in t ? t.username : t.name;
      return !q || name.toLowerCase().includes(q) || t.id.toLowerCase().includes(q);
    });
  }, [targetOptions, search]);

  function selectTarget(id: string) {
    setTarget(id);
    const src = scope === "users" ? permissions!.user_permissions : permissions!.group_permissions;
    setSelected(src?.[id] || []);
    setStatus("");
    setError("");
    setEffective(null);
  }

  function toggle(p: string) {
    setSelected(cur => cur.includes(p) ? cur.filter(x => x !== p) : [...cur, p].sort());
  }

  function setHaPreset(haSet: string[]) {
    setSelected(cur => [...cur.filter(p => !p.startsWith(HA_PREFIX)), ...haSet].sort());
  }

  async function save(perms: string[], msg: string) {
    if (!target) return;
    setSaving(true);
    setStatus("");
    setError("");
    try {
      await updateAdminPermissions(scope, target, perms);
      await load();
      setSelected(perms);
      setStatus(msg);
      if (scope === "users") {
        const data = await fetchEffectivePermissions(target);
        setEffective(data);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (!permissions) {
    return (
      <div style={{ padding: 40, color: J.textSec, fontSize: 13 }}>Loading permissions…</div>
    );
  }

  const currentTarget = targetOptions.find(t => t.id === target);
  const currentName = currentTarget ? ("username" in currentTarget ? currentTarget.username : currentTarget.name) : "";

  const haSelected = selected.filter(p => p.startsWith(HA_PREFIX));
  const platSelected = selected.filter(p => !p.startsWith(HA_PREFIX));
  const hasFullHa = FULL_HA_PERMISSIONS.every(p => selectedSet.has(p));

  const effectivePerms = (effective?.permissions as string[] | undefined) || [];
  const effectiveHa = effectivePerms.filter(p => p.startsWith(HA_PREFIX));
  const effectivePlat = effectivePerms.filter(p => !p.startsWith(HA_PREFIX));

  const row: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
  };
  const cardBase: React.CSSProperties = {
    background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6,
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* ── Metrics row ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 10 }}>
        {[
          { label: "Known permissions", value: permissions.known_permissions.length },
          { label: "HA permissions", value: haPerms.length },
          { label: "User sets", value: Object.keys(permissions.user_permissions).length },
          { label: "Group sets", value: Object.keys(permissions.group_permissions).length },
        ].map(({ label, value }) => (
          <div key={label} style={{ ...cardBase, padding: "12px 16px" }}>
            <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: J.text }}>{value}</div>
          </div>
        ))}
      </div>

      {/* ── Main editor (two columns) ── */}
      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 16, alignItems: "start" }}>

        {/* Left — target list */}
        <div style={{ ...cardBase, overflow: "hidden" }}>
          {/* Scope tabs */}
          <div style={{ display: "flex", borderBottom: `1px solid ${J.border}` }}>
            {(["users", "groups"] as const).map(s => (
              <button key={s} onClick={() => setScope(s)} style={{
                flex: 1, padding: "9px 0", fontSize: 12, fontWeight: 600,
                background: scope === s ? J.amberGlow : "transparent",
                color: scope === s ? J.amber : J.textSec,
                border: "none", cursor: "pointer", textTransform: "capitalize",
                borderBottom: scope === s ? `2px solid ${J.amber}` : "2px solid transparent",
                transition: "background .15s, color .15s",
              }}>{s}</button>
            ))}
          </div>

          {/* Search */}
          {targetOptions.length > 5 && (
            <div style={{ padding: "8px 10px", borderBottom: `1px solid ${J.border}` }}>
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder={`Search ${scope}…`}
                style={{
                  width: "100%", boxSizing: "border-box", padding: "5px 8px", fontSize: 12,
                  background: J.bg3, border: `1px solid ${J.border}`, borderRadius: 4,
                  color: J.text, outline: "none",
                }}
              />
            </div>
          )}

          {/* Target rows */}
          <div style={{ maxHeight: 340, overflowY: "auto" }}>
            {filteredTargets.map(t => {
              const name = "username" in t ? t.username : t.name;
              const active = t.id === target;
              const src = scope === "users" ? permissions.user_permissions : permissions.group_permissions;
              const count = (src?.[t.id] || []).length;
              return (
                <div key={t.id} onClick={() => selectTarget(t.id)} style={{
                  display: "flex", alignItems: "center", gap: 10, padding: "9px 12px", cursor: "pointer",
                  background: active ? J.amberGlow : "transparent",
                  borderLeft: `2px solid ${active ? J.amber : "transparent"}`,
                  borderBottom: `1px solid ${J.border}`,
                  transition: "background .1s",
                }}>
                  <div style={{
                    width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                    background: active ? J.amberDim : J.bg4,
                    border: `1px solid ${active ? J.borderAccent : J.border}`,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 11, fontWeight: 700, color: active ? J.amber : J.textSec,
                  }}>{initials(name)}</div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: active ? 600 : 400, color: active ? J.text : J.textSec, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</div>
                    <div style={{ fontSize: 10, color: J.textMuted }}>{count} permission{count !== 1 ? "s" : ""}</div>
                  </div>
                </div>
              );
            })}
            {filteredTargets.length === 0 && (
              <div style={{ padding: "16px 12px", color: J.textMuted, fontSize: 12 }}>No results.</div>
            )}
          </div>
        </div>

        {/* Right — permission editor */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

          {/* Header */}
          <div style={{ ...cardBase, padding: "14px 18px" }}>
            <div style={{ ...row, justifyContent: "space-between" }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 600, color: J.text }}>{currentName || "—"}</div>
                <div style={{ fontSize: 11, color: J.textMuted, marginTop: 2 }}>
                  {haSelected.length} HA · {platSelected.length} platform · {selected.length} total
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <button
                  onClick={() => void save(selected, "Permissions saved.")}
                  disabled={!target || saving}
                  style={{
                    padding: "6px 16px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
                    background: J.amber, color: J.bg0, border: "none",
                    opacity: !target || saving ? 0.5 : 1, transition: "opacity .15s",
                  }}
                >{saving ? "Saving…" : "Save changes"}</button>
                {scope === "users" && (
                  <button
                    onClick={async () => {
                      if (!target) return;
                      try {
                        setError("");
                        const data = await fetchEffectivePermissions(target);
                        setEffective(data);
                      } catch (err) {
                        setError((err as Error).message);
                      }
                    }}
                    disabled={!target}
                    style={{
                      padding: "6px 12px", fontSize: 12, borderRadius: 4, cursor: "pointer",
                      background: "transparent", color: J.textSec,
                      border: `1px solid ${J.border}`,
                      opacity: !target ? 0.5 : 1,
                    }}
                  >Show effective</button>
                )}
              </div>
            </div>
            {status && <div style={{ marginTop: 8, fontSize: 12, color: J.success }}>{status}</div>}
            {error && <div style={{ marginTop: 8, fontSize: 12, color: J.error }}>{error}</div>}
          </div>

          {/* HA bundle preset */}
          <div style={{ ...cardBase, padding: "14px 18px" }}>
            <div style={{ ...row, justifyContent: "space-between" }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: J.text }}>Home Assistant — Full Access</div>
                <div style={{ fontSize: 11, color: J.textMuted, marginTop: 2 }}>Grants all {FULL_HA_PERMISSIONS.length} HA permissions in one step.</div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                {hasFullHa ? (
                  <button
                    onClick={() => setHaPreset([])}
                    style={{ padding: "5px 12px", fontSize: 11, borderRadius: 4, cursor: "pointer", background: J.errorDim, color: J.error, border: `1px solid ${J.error}30` }}
                  >Clear HA</button>
                ) : (
                  <button
                    onClick={() => setHaPreset(FULL_HA_PERMISSIONS)}
                    style={{ padding: "5px 12px", fontSize: 11, borderRadius: 4, cursor: "pointer", background: J.amberDim, color: J.amber, border: `1px solid ${J.borderAccent}` }}
                  >Select all HA</button>
                )}
                <button
                  onClick={() => void save([...selected.filter(p => !p.startsWith(HA_PREFIX)), ...FULL_HA_PERMISSIONS].sort(), "Full HA access saved.")}
                  disabled={!target || saving}
                  style={{ padding: "5px 12px", fontSize: 11, borderRadius: 4, cursor: "pointer", background: J.amber, color: J.bg0, border: "none", opacity: !target || saving ? 0.5 : 1 }}
                >Save full HA</button>
              </div>
            </div>
          </div>

          {/* Permission toggles */}
          {haPerms.length > 0 && (
            <div style={{ ...cardBase, padding: "14px 18px" }}>
              <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>Home Assistant</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {haPerms.map(p => {
                  const on = selectedSet.has(p);
                  return (
                    <button key={p} onClick={() => toggle(p)} style={{
                      padding: "4px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                      background: on ? J.amberDim : J.bg4,
                      color: on ? J.amber : J.textSec,
                      border: `1px solid ${on ? J.borderAccent : J.border}`,
                      fontWeight: on ? 600 : 400, transition: "all .1s",
                    }}>{labelFor(p)}</button>
                  );
                })}
              </div>
            </div>
          )}

          {platformPerms.length > 0 && (
            <div style={{ ...cardBase, padding: "14px 18px" }}>
              <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>Platform</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {platformPerms.map(p => {
                  const on = selectedSet.has(p);
                  return (
                    <button key={p} onClick={() => toggle(p)} style={{
                      padding: "4px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                      background: on ? J.blueDim : J.bg4,
                      color: on ? J.blue : J.textSec,
                      border: `1px solid ${on ? J.blue + "40" : J.border}`,
                      fontWeight: on ? 600 : 400, transition: "all .1s",
                    }}>{labelFor(p)}</button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Effective permissions panel */}
          {effective && (
            <div style={{ ...cardBase, padding: "14px 18px" }}>
              <div style={{ ...row, justifyContent: "space-between", marginBottom: 12 }}>
                <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Effective permissions</div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  {typeof effective.source === "string" && <span style={{ fontSize: 10, color: J.textMuted, background: J.bg4, border: `1px solid ${J.border}`, borderRadius: 3, padding: "2px 6px" }}>{effective.source}</span>}
                  <span style={{ fontSize: 11, color: J.textMuted }}>{effectivePerms.length} total</span>
                  <button onClick={() => setEffective(null)} style={{ padding: "2px 8px", fontSize: 10, borderRadius: 3, cursor: "pointer", background: "transparent", color: J.textMuted, border: `1px solid ${J.border}` }}>×</button>
                </div>
              </div>
              {effectiveHa.length > 0 && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 10, color: J.textMuted, marginBottom: 6 }}>Home Assistant</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                    {effectiveHa.map(p => (
                      <span key={p} style={{ fontSize: 10, padding: "3px 8px", borderRadius: 3, background: J.successDim, color: J.success, border: `1px solid ${J.success}30` }}>{labelFor(p)}</span>
                    ))}
                  </div>
                </div>
              )}
              {effectivePlat.length > 0 && (
                <div>
                  <div style={{ fontSize: 10, color: J.textMuted, marginBottom: 6 }}>Platform</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                    {effectivePlat.map(p => (
                      <span key={p} style={{ fontSize: 10, padding: "3px 8px", borderRadius: 3, background: J.blueDim, color: J.blue, border: `1px solid ${J.blue}30` }}>{labelFor(p)}</span>
                    ))}
                  </div>
                </div>
              )}
              {effectivePerms.length === 0 && (
                <div style={{ fontSize: 12, color: J.textMuted }}>No permissions granted.</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
