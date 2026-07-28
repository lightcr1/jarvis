import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";
import { getStoredPreferences } from "../api/client";
import { J, useJ, IconMoon, IconSun, IconFolder, IconMail, IconCalendar, IconMonitor, applyTheme } from "../../screens/jarvis-shared";
import { AppSwitcher } from "./AppSwitcher";

const NAV_LINKS = [
  { to: "/workspace/files", label: "Files", icon: IconFolder },
  { to: "/workspace/email", label: "Email", icon: IconMail },
  { to: "/workspace/calendar", label: "Calendar", icon: IconCalendar },
  { to: "/workspace/desktop", label: "Desktop", icon: IconMonitor },
];

// Inject mobile nav styles once — distinct class names from JarvisApp's
// .nav-rail/.nav-bottom so the two shells never share a hidden dependency.
(function () {
  if (document.getElementById("jarvis-workspace-nav-styles")) return;
  const s = document.createElement("style");
  s.id = "jarvis-workspace-nav-styles";
  s.textContent = `
    .ws-sidebar     { display: flex; }
    .ws-bottom-nav  { display: none; }
    .ws-mobile-only { display: none; }
    @media (max-width: 640px) {
      .ws-sidebar     { display: none !important; }
      .ws-bottom-nav  { display: flex !important; }
      .ws-mobile-only { display: flex !important; }
    }
  `;
  document.head.appendChild(s);
})();

export function WorkspaceShell() {
  useJ();
  const { user, loading, logout, preferences, savePreferences } = useAuth();
  const navigate = useNavigate();
  const [showSwitcher, setShowSwitcher] = useState(false);
  const [showMobileSwitcher, setShowMobileSwitcher] = useState(false);
  const [mobilePad, setMobilePad] = useState(false);
  const isDark = (preferences.theme ?? "dark") === "dark";

  useEffect(() => {
    const storedTheme = getStoredPreferences().theme;
    if (storedTheme) applyTheme(storedTheme as "dark" | "light");
  }, []);

  useEffect(() => {
    const update = () => setMobilePad(window.innerWidth <= 640);
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user) navigate("/", { replace: true });
  }, [loading, user, navigate]);

  if (loading || !user) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: J.bg0, color: J.textSec, fontSize: 13 }}>
        Loading workspace…
      </div>
    );
  }

  const userInitial = (user.username?.[0] ?? "U").toUpperCase();

  const toggleTheme = () => {
    const next = isDark ? "light" : "dark";
    applyTheme(next);
    void savePreferences({ ...preferences, theme: next });
  };

  return (
    <div style={{ display: "flex", height: "100vh", background: J.bg0, color: J.text, overflow: "hidden" }}>
      {/* Sidebar — desktop only, collapses to bottom tab bar below 640px */}
      <aside
        className="ws-sidebar"
        style={{ width: 200, flexShrink: 0, background: J.bg1, borderRight: `1px solid ${J.border}`, flexDirection: "column", overflow: "hidden" }}
      >
        <div style={{ position: "relative", borderBottom: `1px solid ${J.border}` }}>
          <button
            onClick={() => setShowSwitcher(v => !v)}
            style={{ width: "100%", textAlign: "left", display: "flex", alignItems: "center", gap: 10, padding: "16px 16px 12px", background: "none", border: "none", cursor: "pointer" }}
          >
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 8,
                background: J.amberDim,
                border: `1px solid ${J.borderAccent}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 14,
                fontWeight: 700,
                color: J.amber,
                flexShrink: 0,
              }}
            >
              J
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: J.text }}>Jarvis Workspace</div>
              <div style={{ fontSize: 10, color: J.textMuted }}>Files · Mail · Calendar · Desktop</div>
            </div>
          </button>
          {showSwitcher && <AppSwitcher current="workspace" onClose={() => setShowSwitcher(false)} placement="below" />}
        </div>

        <nav style={{ flex: 1, padding: "8px 8px", display: "flex", flexDirection: "column", gap: 2, overflowY: "auto" }}>
          {NAV_LINKS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end
              style={({ isActive }) => ({
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "7px 10px",
                borderRadius: 6,
                fontSize: 13,
                textDecoration: "none",
                transition: "all .1s",
                background: isActive ? J.amberGlow : "transparent",
                color: isActive ? J.amber : J.textSec,
                borderLeft: `2px solid ${isActive ? J.amber : "transparent"}`,
                fontWeight: isActive ? 600 : 400,
              })}
            >
              <Icon size={14} /> {label}
            </NavLink>
          ))}
        </nav>

        <div style={{ padding: "12px 12px", borderTop: `1px solid ${J.border}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <div
              style={{
                width: 26,
                height: 26,
                borderRadius: "50%",
                background: J.bg4,
                border: `1px solid ${J.border}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 11,
                fontWeight: 700,
                color: J.textSec,
                flexShrink: 0,
              }}
            >
              {userInitial}
            </div>
            <div style={{ minWidth: 0, overflow: "hidden" }}>
              <div style={{ fontSize: 12, color: J.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.username}</div>
            </div>
          </div>
          <button
            onClick={() => logout().then(() => navigate("/"))}
            style={{ width: "100%", padding: "6px 10px", fontSize: 12, borderRadius: 5, cursor: "pointer", background: J.errorDim, color: J.error, border: `1px solid ${J.error}30` }}
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Main area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <header
          style={{ height: 52, flexShrink: 0, background: J.bg1, borderBottom: `1px solid ${J.border}`, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px" }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, position: "relative" }}>
            <button
              className="ws-mobile-only"
              onClick={() => setShowMobileSwitcher(v => !v)}
              style={{
                width: 30,
                height: 30,
                borderRadius: 8,
                background: J.amberDim,
                border: `1px solid ${J.borderAccent}`,
                alignItems: "center",
                justifyContent: "center",
                fontSize: 13,
                fontWeight: 700,
                color: J.amber,
                cursor: "pointer",
              }}
            >
              J
            </button>
            {showMobileSwitcher && <AppSwitcher current="workspace" onClose={() => setShowMobileSwitcher(false)} placement="below" />}
            <div>
              <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Workspace</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: J.text }}>Jarvis Workspace</div>
            </div>
          </div>
          <button
            onClick={toggleTheme}
            title={isDark ? "Switch to light mode" : "Switch to dark mode"}
            style={{
              width: 32,
              height: 32,
              borderRadius: 7,
              background: "transparent",
              border: `1px solid ${J.border}`,
              color: J.textMuted,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transition: "all .15s",
            }}
            onMouseEnter={e => {
              const el = e.currentTarget;
              el.style.color = J.amber;
              el.style.borderColor = J.borderAccent;
            }}
            onMouseLeave={e => {
              const el = e.currentTarget;
              el.style.color = J.textMuted;
              el.style.borderColor = J.border;
            }}
          >
            {isDark ? <IconSun size={14} /> : <IconMoon size={14} />}
          </button>
        </header>
        <main style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column", paddingBottom: mobilePad ? 60 : 0 }}>
          <Outlet />
        </main>
      </div>

      {/* Bottom tab bar — mobile only */}
      <nav
        className="ws-bottom-nav"
        aria-label="Workspace navigation"
        style={{ position: "fixed", bottom: 0, left: 0, right: 0, height: 60, background: J.bg1, borderTop: `1px solid ${J.border}`, flexDirection: "row", alignItems: "center", justifyContent: "space-around", zIndex: 100, paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        {NAV_LINKS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end
            style={({ isActive }) => ({
              flex: 1,
              height: "100%",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 3,
              textDecoration: "none",
              color: isActive ? J.amber : J.textMuted,
              transition: "color .12s",
            })}
          >
            <Icon size={18} />
            <span style={{ fontSize: 10, fontWeight: 500 }}>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
