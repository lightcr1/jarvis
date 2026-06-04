import React, { useCallback, useEffect, useState } from "react";
import {
  AdminUser,
  createAdminUser,
  deleteAdminUser,
  deleteAdminUserConversations,
  fetchAdminUsers,
  setAdminUserPassword,
  updateAdminUser,
} from "../../../shared/api/admin";
import { useJ } from "../../../screens/jarvis-shared";

const ROLES = ["admin", "standard_user", "guest_restricted", "service_system"] as const;
type Role = typeof ROLES[number];

function roleColor(role: string, J: ReturnType<typeof useJ>): { bg: string; color: string } {
  if (role === "admin") return { bg: J.amberDim, color: J.amber };
  if (role === "guest_restricted") return { bg: J.warnDim, color: J.warn };
  if (role === "service_system") return { bg: J.blueDim, color: J.blue };
  return { bg: J.bg4, color: J.textSec };
}

function initials(name: string) {
  return name.slice(0, 2).toUpperCase();
}

function PasswordReset({ user, onDone }: { user: AdminUser; onDone: (msg: string) => void }) {
  const J = useJ();
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState("");
  const [saving, setSaving] = useState(false);

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} style={{
        padding: "3px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer",
        background: "transparent", color: J.textSec, border: `1px solid ${J.border}`,
      }}>Password</button>
    );
  }

  const submit = async () => {
    if (!pw.trim()) return;
    setSaving(true);
    try {
      await setAdminUserPassword(user.id, pw.trim());
      onDone(`Password updated for ${user.username}.`);
      setPw("");
      setOpen(false);
    } catch (e) {
      onDone(`Error: ${e instanceof Error ? e.message : "Failed."}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
      <input
        autoFocus
        type="password"
        value={pw}
        onChange={e => setPw(e.target.value)}
        onKeyDown={e => { if (e.key === "Enter") void submit(); if (e.key === "Escape") { setOpen(false); setPw(""); } }}
        placeholder="New password"
        style={{
          width: 120, padding: "4px 8px", fontSize: 11, borderRadius: 4,
          background: J.bg3, border: `1px solid ${J.border}`, color: J.text, outline: "none",
        }}
      />
      <button onClick={() => void submit()} disabled={saving} style={{
        padding: "4px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer",
        background: J.amber, color: J.bg0, border: "none", opacity: saving ? 0.6 : 1,
      }}>{saving ? "…" : "Set"}</button>
      <button onClick={() => { setOpen(false); setPw(""); }} style={{
        padding: "4px 8px", fontSize: 11, borderRadius: 4, cursor: "pointer",
        background: "transparent", color: J.textMuted, border: `1px solid ${J.border}`,
      }}>✕</button>
    </div>
  );
}

export function UsersPage() {
  const J = useJ();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [search, setSearch] = useState("");
  const [form, setForm] = useState({ username: "", role: "standard_user" as Role, enabled: true, password: "" });
  const [creating, setCreating] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const load = useCallback(() => fetchAdminUsers().then(d => setUsers(d.users || [])), []);
  useEffect(() => { load().catch(() => undefined); }, [load]);
  useEffect(() => {
    if (!status) return;
    const id = setTimeout(() => setStatus(""), 4000);
    return () => clearTimeout(id);
  }, [status]);

  const filtered = users.filter(u => {
    const q = search.toLowerCase();
    return !q || u.username.toLowerCase().includes(q) || u.role.toLowerCase().includes(q) || u.id.includes(q);
  });

  const allSelected = filtered.length > 0 && filtered.every(u => selected.has(u.id));
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(filtered.map(u => u.id)));
  const toggleOne = (id: string) => setSelected(prev => {
    const s = new Set(prev);
    s.has(id) ? s.delete(id) : s.add(id);
    return s;
  });

  const bulkOp = async (op: "enable" | "disable" | "delete") => {
    const ids = [...selected].filter(id => filtered.some(u => u.id === id));
    if (!ids.length) return;
    if (op === "delete" && !window.confirm(`Delete ${ids.length} user(s)? This cannot be undone.`)) return;
    setBulkBusy(true);
    try {
      if (op === "delete") {
        await Promise.all(ids.map(id => deleteAdminUser(id)));
        setStatus(`Deleted ${ids.length} user(s).`);
      } else {
        await Promise.all(ids.map(id => updateAdminUser(id, { enabled: op === "enable" })));
        setStatus(`${op === "enable" ? "Enabled" : "Disabled"} ${ids.length} user(s).`);
      }
      setSelected(new Set());
      await load();
    } catch (e) { setStatus(`Error: ${e instanceof Error ? e.message : "Bulk op failed."}`); }
    finally { setBulkBusy(false); }
  };

  const createUser = async () => {
    if (!form.username.trim()) return;
    setCreating(true);
    try {
      await createAdminUser(form);
      setForm({ username: "", role: "standard_user", enabled: true, password: "" });
      setStatus("User created.");
      setShowCreate(false);
      await load();
    } catch (e) {
      setStatus(`Error: ${e instanceof Error ? e.message : "Failed to create user."}`);
    } finally {
      setCreating(false);
    }
  };

  const enabledCount = users.filter(u => u.enabled).length;
  const adminCount = users.filter(u => u.role === "admin").length;
  const card: React.CSSProperties = {
    background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6,
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>

      {/* ── Metrics ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: 10 }}>
        {[
          { label: "Total", value: users.length },
          { label: "Enabled", value: enabledCount, accent: J.success },
          { label: "Admins", value: adminCount, accent: J.amber },
          { label: "Disabled", value: users.length - enabledCount, accent: users.length - enabledCount > 0 ? J.warn : undefined },
        ].map(({ label, value, accent }) => (
          <div key={label} style={{ ...card, padding: "12px 16px" }}>
            <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: accent || J.text }}>{value}</div>
          </div>
        ))}
      </div>

      {/* ── Toolbar ── */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search users…"
          style={{
            flex: 1, minWidth: 180, padding: "6px 10px", fontSize: 13, borderRadius: 4,
            background: J.bg2, border: `1px solid ${J.border}`, color: J.text, outline: "none",
          }}
        />
        <button onClick={() => setShowCreate(v => !v)} style={{
          padding: "6px 14px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
          background: showCreate ? J.amberDim : J.amber, color: showCreate ? J.amber : J.bg0,
          border: showCreate ? `1px solid ${J.borderAccent}` : "none",
        }}>
          {showCreate ? "Cancel" : "+ New user"}
        </button>
        {status && <span style={{ fontSize: 11, color: status.startsWith("Error") ? J.error : J.success }}>{status}</span>}
      </div>

      {/* ── Create form ── */}
      {showCreate && (
        <div style={{ ...card, padding: "16px 18px" }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: J.text, marginBottom: 12 }}>Create user</div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div style={{ flex: "1 1 160px" }}>
              <div style={{ fontSize: 10, color: J.textMuted, marginBottom: 4 }}>Username</div>
              <input
                value={form.username}
                onChange={e => setForm({ ...form, username: e.target.value })}
                onKeyDown={e => e.key === "Enter" && void createUser()}
                placeholder="username"
                autoFocus
                style={{ width: "100%", boxSizing: "border-box", padding: "6px 10px", fontSize: 12, borderRadius: 4, background: J.bg3, border: `1px solid ${J.border}`, color: J.text, outline: "none" }}
              />
            </div>
            <div style={{ flex: "1 1 140px" }}>
              <div style={{ fontSize: 10, color: J.textMuted, marginBottom: 4 }}>Role</div>
              <select
                value={form.role}
                onChange={e => setForm({ ...form, role: e.target.value as Role })}
                style={{ width: "100%", boxSizing: "border-box", padding: "6px 10px", fontSize: 12, borderRadius: 4, background: J.bg3, border: `1px solid ${J.border}`, color: J.text, outline: "none" }}
              >
                {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div style={{ flex: "1 1 140px" }}>
              <div style={{ fontSize: 10, color: J.textMuted, marginBottom: 4 }}>Password</div>
              <input
                type="password"
                value={form.password}
                onChange={e => setForm({ ...form, password: e.target.value })}
                placeholder="initial password"
                style={{ width: "100%", boxSizing: "border-box", padding: "6px 10px", fontSize: 12, borderRadius: 4, background: J.bg3, border: `1px solid ${J.border}`, color: J.text, outline: "none" }}
              />
            </div>
            <button onClick={() => void createUser()} disabled={!form.username.trim() || creating} style={{
              padding: "6px 16px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
              background: J.amber, color: J.bg0, border: "none",
              opacity: !form.username.trim() || creating ? 0.5 : 1,
            }}>{creating ? "Creating…" : "Create"}</button>
          </div>
        </div>
      )}

      {/* ── Bulk bar ── */}
      {selected.size > 0 && (
        <div style={{ ...card, padding: "8px 14px", display: "flex", alignItems: "center", gap: 10, borderColor: J.borderAccent }}>
          <span style={{ fontSize: 12, color: J.amber, fontWeight: 600 }}>{selected.size} selected</span>
          <button onClick={() => void bulkOp("enable")} disabled={bulkBusy} style={{ padding: "3px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer", background: J.successDim, color: J.success, border: `1px solid ${J.success}30` }}>Enable</button>
          <button onClick={() => void bulkOp("disable")} disabled={bulkBusy} style={{ padding: "3px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer", background: J.warnDim, color: J.warn, border: `1px solid ${J.warn}30` }}>Disable</button>
          <button onClick={() => void bulkOp("delete")} disabled={bulkBusy} style={{ padding: "3px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer", background: J.errorDim, color: J.error, border: `1px solid ${J.error}30` }}>Delete</button>
          <button onClick={() => setSelected(new Set())} style={{ padding: "3px 8px", fontSize: 11, borderRadius: 4, cursor: "pointer", background: "transparent", color: J.textMuted, border: `1px solid ${J.border}`, marginLeft: "auto" }}>✕ Clear</button>
        </div>
      )}

      {/* ── User list ── */}
      <div style={{ ...card, overflow: "hidden" }}>
        {/* Header */}
        <div style={{
          display: "grid", gridTemplateColumns: "32px 1fr 130px 90px 90px 120px 1fr",
          gap: 0, padding: "8px 14px",
          borderBottom: `1px solid ${J.border}`,
          fontSize: 10, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em",
          background: J.bg1,
        }}>
          <div><input type="checkbox" checked={allSelected} onChange={toggleAll} style={{ accentColor: J.amber }} /></div>
          <div>User</div>
          <div>Role</div>
          <div>Status</div>
          <div>Session</div>
          <div>ID</div>
          <div>Actions</div>
        </div>

        {filtered.length === 0 && (
          <div style={{ padding: "24px 18px", color: J.textMuted, fontSize: 13 }}>
            {search ? "No users match the search." : "No users."}
          </div>
        )}

        {filtered.map((u, i) => {
          const rc = roleColor(u.role, J);
          const isSelected = selected.has(u.id);
          return (
            <div key={u.id} style={{
              display: "grid", gridTemplateColumns: "32px 1fr 130px 90px 90px 120px 1fr",
              gap: 0, padding: "10px 14px", alignItems: "center",
              borderBottom: i < filtered.length - 1 ? `1px solid ${J.border}` : "none",
              background: isSelected ? J.amberGlow : i % 2 === 1 ? J.bg1 : "transparent",
              transition: "background .1s",
            }}>
              <div>
                <input type="checkbox" checked={isSelected} onChange={() => toggleOne(u.id)} style={{ accentColor: J.amber }} />
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{
                  width: 30, height: 30, borderRadius: "50%", flexShrink: 0,
                  background: J.bg4, border: `1px solid ${J.border}`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 11, fontWeight: 700, color: J.textSec,
                }}>{initials(u.username)}</div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: J.text }}>{u.username}</div>
                  <div style={{ fontSize: 10, color: J.textMuted }}>
                    {u.last_seen_at
                      ? `Last seen ${new Date(u.last_seen_at * 1000).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}`
                      : u.role === "admin" ? "Dashboard access" : "Never logged in"}
                  </div>
                </div>
              </div>
              <div>
                <span style={{ fontSize: 11, padding: "2px 7px", borderRadius: 3, ...rc }}>{u.role}</span>
              </div>
              <div>
                <span style={{
                  fontSize: 11, padding: "2px 7px", borderRadius: 3,
                  background: u.enabled ? J.successDim : J.errorDim,
                  color: u.enabled ? J.success : J.error,
                }}>{u.enabled ? "enabled" : "disabled"}</span>
              </div>
              <div>
                {u.active_session
                  ? <span style={{ fontSize: 11, padding: "2px 7px", borderRadius: 3, background: J.successDim, color: J.success }}>active</span>
                  : <span style={{ fontSize: 11, color: J.textMuted }}>—</span>}
              </div>
              <div>
                <code style={{ fontSize: 10, color: J.textMuted, fontFamily: "monospace", background: J.bg4, padding: "2px 5px", borderRadius: 3 }}>{u.id.slice(0, 8)}…</code>
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <button onClick={async () => {
                  try {
                    await updateAdminUser(u.id, { enabled: !u.enabled });
                    await load();
                  } catch (e) { setStatus(`Error: ${e instanceof Error ? e.message : "Failed."}`); }
                }} style={{
                  padding: "3px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                  background: u.enabled ? J.warnDim : J.successDim,
                  color: u.enabled ? J.warn : J.success,
                  border: `1px solid ${u.enabled ? J.warn + "30" : J.success + "30"}`,
                }}>{u.enabled ? "Disable" : "Enable"}</button>
                <PasswordReset user={u} onDone={setStatus} />
                <button onClick={async () => {
                  if (!window.confirm(`Clear all chat history for "${u.username}"? This cannot be undone.`)) return;
                  try {
                    const r = await deleteAdminUserConversations(u.id);
                    setStatus(`Deleted ${r.deleted} conversation(s) for ${u.username}.`);
                  } catch (e) { setStatus(`Error: ${e instanceof Error ? e.message : "Failed."}`); }
                }} style={{
                  padding: "3px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                  background: J.warnDim, color: J.warn, border: `1px solid ${J.warn}30`,
                }}>Clear chats</button>
                <button onClick={async () => {
                  if (!window.confirm(`Delete "${u.username}"? This cannot be undone.`)) return;
                  try {
                    await deleteAdminUser(u.id);
                    await load();
                    setStatus(`Deleted ${u.username}.`);
                  } catch (e) { setStatus(`Error: ${e instanceof Error ? e.message : "Failed."}`); }
                }} style={{
                  padding: "3px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                  background: J.errorDim, color: J.error, border: `1px solid ${J.error}30`,
                }}>Delete</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
