import React, { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";
import { getStoredPreferences } from "../api/client";
import { J, useJ, IconMoon, IconSun, IconJarvisMark, applyTheme, applyAccent, applyCompact, ToastContainer } from "../../screens/jarvis-shared";
import { AppSwitcher } from "./AppSwitcher";
import { AppearancePanel } from "../ui/AppearancePanel";
import { OverlayDialog } from "../ui/OverlayDialog";

export function MonitorShell() {
  useJ();
  const { isAdmin, loading, ensureAdminAccess, user, logout } = useAuth();
  const navigate = useNavigate();
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");
  const [showSwitcher, setShowSwitcher] = useState(false);
  const [showPreferences, setShowPreferences] = useState(false);
  
  useEffect(() => {
    const storedPrefs = getStoredPreferences();
    if (storedPrefs.theme) applyTheme(storedPrefs.theme as "dark" | "light");
    if (storedPrefs.accent_color) applyAccent(storedPrefs.accent_color);
    applyCompact(storedPrefs.compact_mode ?? false);
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!isAdmin) { navigate("/dashboard/login", { replace: true }); return; }
    ensureAdminAccess()
      .then(() => setBooting(false))
      .catch((err: Error) => { setError(err.message); navigate("/dashboard/login", { replace: true }); });
  }, [ensureAdminAccess, isAdmin, loading, navigate]);

  useEffect(() => {
    const handleAdminExpired = () => {
      if (!isAdmin) return;
      ensureAdminAccess().catch(() => navigate("/dashboard/login", { replace: true }));
    };
    window.addEventListener("jarvis:admin-session-expired", handleAdminExpired);
    return () => window.removeEventListener("jarvis:admin-session-expired", handleAdminExpired);
  }, [ensureAdminAccess, isAdmin, navigate]);

  if (loading || booting) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: J.bg0, color: J.textSec, fontSize: 13 }}>
        Loading Monitor…
      </div>
    );
  }

  const userInitial = (user?.username?.[0] ?? "A").toUpperCase();

  return (
    <div style={{ display: "flex", height: "100vh", background: J.bg0, color: J.text, overflow: "hidden" }}>
      {/* ── Sidebar ── */}
      <aside style={{
        width: 200, flexShrink: 0, background: J.bg1, borderRight: `1px solid ${J.border}`,
        display: "flex", flexDirection: "column", overflow: "hidden",
      }}>
        <div style={{ position: "relative", borderBottom: `1px solid ${J.border}` }}>
          <button onClick={() => setShowSwitcher(v => !v)} style={{ width: "100%", textAlign: "left", background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 10, padding: "16px 16px 12px" }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8, background: J.amberDim,
              border: `1px solid ${J.borderAccent}`, display: "flex", alignItems: "center",
              justifyContent: "center", color: J.amber, flexShrink: 0,
            }}><IconJarvisMark size={17} /></div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: J.text }}>Agent Monitor</div>
              <div style={{ fontSize: 10, color: J.textMuted }}>Live Jarvis-Aktivität</div>
            </div>
          </button>
          {showSwitcher && <AppSwitcher current="monitor" onClose={() => setShowSwitcher(false)} placement="below" />}
        </div>

        <nav style={{ flex: 1, padding: "8px 8px", display: "flex", flexDirection: "column", gap: 2, overflowY: "auto" }}>
          <NavLink to="/monitor" end style={({ isActive }) => ({
            display: "block", padding: "7px 10px", borderRadius: 6, fontSize: 13,
            textDecoration: "none", transition: "all .1s",
            background: isActive ? J.amberGlow : "transparent",
            color: isActive ? J.amber : J.textSec,
            borderLeft: `2px solid ${isActive ? J.amber : "transparent"}`,
            fontWeight: isActive ? 600 : 400,
          })}>
            Übersicht
          </NavLink>
          <NavLink to="/dashboard/agent" style={({ isActive }) => ({
            display: "block", padding: "7px 10px", borderRadius: 6, fontSize: 13,
            textDecoration: "none", transition: "all .1s",
            background: isActive ? J.amberGlow : "transparent",
            color: isActive ? J.amber : J.textSec,
            borderLeft: `2px solid ${isActive ? J.amber : "transparent"}`,
            fontWeight: isActive ? 600 : 400,
          })}>
            Klassische Ansicht
          </NavLink>
        </nav>

        <div style={{ padding: "12px 12px", borderTop: `1px solid ${J.border}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <div style={{
              width: 26, height: 26, borderRadius: "50%", background: J.bg4, border: `1px solid ${J.border}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 11, fontWeight: 700, color: J.textSec, flexShrink: 0,
            }}>{userInitial}</div>
            <div style={{ minWidth: 0, overflow: "hidden" }}>
              <div style={{ fontSize: 12, color: J.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user?.username ?? "Admin"}</div>
              <div style={{ fontSize: 10, color: J.textMuted }}>admin</div>
            </div>
          </div>
          <button
            onClick={() => setShowPreferences(true)}
            style={{
              width: "100%", padding: "6px 10px", fontSize: 12, borderRadius: 5, cursor: "pointer", marginBottom: 6,
              background: "transparent", color: J.textSec, border: `1px solid ${J.border}`,
            }}
          >Preferences</button>
          <button
            onClick={() => logout().then(() => navigate("/chat"))}
            style={{
              width: "100%", padding: "6px 10px", fontSize: 12, borderRadius: 5, cursor: "pointer",
              background: J.errorDim, color: J.error, border: `1px solid ${J.error}30`,
            }}
          >Sign out</button>
        </div>
      </aside>

      {/* ── Content ── */}
      <main style={{ flex: 1, overflowY: "auto", padding: "24px 28px" }}>
        {error && (
          <div style={{ background: J.errorDim, color: J.error, padding: "10px 14px", borderRadius: 6, marginBottom: 14, fontSize: 13 }}>
            {error}
          </div>
        )}
        <Outlet />
      </main>

      {showPreferences && (
        <OverlayDialog title="Preferences" onClose={() => setShowPreferences(false)}>
          <AppearancePanel />
        </OverlayDialog>
      )}
      <ToastContainer />
    </div>
  );
}
