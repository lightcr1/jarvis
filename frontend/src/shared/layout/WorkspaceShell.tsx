import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";
import { getStoredPreferences } from "../api/client";
import { J, useJ, IconMoon, IconSun, IconGrid, applyTheme, applyAccent, applyCompact, ToastContainer } from "../../screens/jarvis-shared";
import { AppSwitcher } from "./AppSwitcher";
import { WorkspaceLauncher, workspaceAppFromPath } from "./WorkspaceLauncher";
import { AppearancePanel } from "../ui/AppearancePanel";
import { OverlayDialog } from "../ui/OverlayDialog";

const APP_TITLES: Record<string, string> = {
  drive: "Drive",
  communication: "Kommunikation",
  desktop: "Desktop",
};

export function WorkspaceShell() {
  useJ();
  const { user, loading, logout, preferences, savePreferences } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [showSwitcher, setShowSwitcher] = useState(false);
  const [showLauncher, setShowLauncher] = useState(false);
  const [showAccount, setShowAccount] = useState(false);
  const [showPreferences, setShowPreferences] = useState(false);
  const isDark = (preferences.theme ?? "dark") === "dark";
  const currentApp = workspaceAppFromPath(location.pathname);

  useEffect(() => {
    const storedPrefs = getStoredPreferences();
    if (storedPrefs.theme) applyTheme(storedPrefs.theme as "dark" | "light");
    if (storedPrefs.accent_color) applyAccent(storedPrefs.accent_color);
    applyCompact(storedPrefs.compact_mode ?? false);
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
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: J.bg0, color: J.text, overflow: "hidden" }}>
      <header
        style={{ height: 52, flexShrink: 0, background: J.bg1, borderBottom: `1px solid ${J.border}`, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 16px", gap: 12 }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
          <div style={{ position: "relative", flexShrink: 0 }}>
            <button
              onClick={() => setShowSwitcher(v => !v)}
              aria-label="Switch area"
              style={{ width: 32, height: 32, borderRadius: 8, background: J.amberDim, border: `1px solid ${J.borderAccent}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, color: J.amber, cursor: "pointer" }}
            >
              J
            </button>
            {showSwitcher && <AppSwitcher current="workspace" onClose={() => setShowSwitcher(false)} placement="below" />}
          </div>
          <div style={{ position: "relative", flexShrink: 0 }}>
            <button
              onClick={() => setShowLauncher(v => !v)}
              aria-label="Workspace apps"
              title="Workspace apps"
              style={{ width: 32, height: 32, borderRadius: 8, background: "transparent", border: `1px solid ${J.border}`, display: "flex", alignItems: "center", justifyContent: "center", color: J.textSec, cursor: "pointer" }}
              onMouseEnter={e => { e.currentTarget.style.color = J.amber; e.currentTarget.style.borderColor = J.borderAccent; }}
              onMouseLeave={e => { e.currentTarget.style.color = J.textSec; e.currentTarget.style.borderColor = J.border; }}
            >
              <IconGrid size={14} />
            </button>
            {showLauncher && <WorkspaceLauncher current={currentApp} onClose={() => setShowLauncher(false)} />}
          </div>
          <div style={{ minWidth: 0, overflow: "hidden" }}>
            <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Workspace</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: J.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{APP_TITLES[currentApp]}</div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          <button
            onClick={toggleTheme}
            title={isDark ? "Switch to light mode" : "Switch to dark mode"}
            style={{ width: 32, height: 32, borderRadius: 7, background: "transparent", border: `1px solid ${J.border}`, color: J.textMuted, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", transition: "all .15s" }}
            onMouseEnter={e => { e.currentTarget.style.color = J.amber; e.currentTarget.style.borderColor = J.borderAccent; }}
            onMouseLeave={e => { e.currentTarget.style.color = J.textMuted; e.currentTarget.style.borderColor = J.border; }}
          >
            {isDark ? <IconSun size={14} /> : <IconMoon size={14} />}
          </button>
          <div style={{ position: "relative" }}>
            <button
              onClick={() => setShowAccount(v => !v)}
              style={{ width: 32, height: 32, borderRadius: 8, background: J.bg3, border: `1px solid ${J.border}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 600, color: J.textSec, cursor: "pointer" }}
            >
              {userInitial}
            </button>
            {showAccount && (
              <>
                <div onClick={() => setShowAccount(false)} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
                <div
                  style={{
                    position: "absolute", top: "calc(100% + 8px)", right: 0, width: 180, background: J.bg2, border: `1px solid ${J.border}`,
                    borderRadius: 10, zIndex: 41, overflow: "hidden", boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                  }}
                >
                  <div style={{ padding: "10px 14px", fontSize: 12, color: J.text, borderBottom: `1px solid ${J.border}`, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {user.username}
                  </div>
                  <button
                    onClick={() => { setShowAccount(false); setShowPreferences(true); }}
                    style={{ width: "100%", textAlign: "left", padding: "10px 14px", background: "none", border: "none", color: J.textSec, fontSize: 13, cursor: "pointer" }}
                    onMouseEnter={e => { e.currentTarget.style.background = J.bg3; e.currentTarget.style.color = J.text; }}
                    onMouseLeave={e => { e.currentTarget.style.background = "none"; e.currentTarget.style.color = J.textSec; }}
                  >
                    Preferences
                  </button>
                  <button
                    onClick={() => { setShowAccount(false); logout().then(() => navigate("/")); }}
                    style={{ width: "100%", textAlign: "left", padding: "10px 14px", background: "none", border: "none", color: J.error, fontSize: 13, cursor: "pointer" }}
                    onMouseEnter={e => { e.currentTarget.style.background = J.bg3; }}
                    onMouseLeave={e => { e.currentTarget.style.background = "none"; }}
                  >
                    Sign out
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      <main style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <Outlet />
      </main>

      {showPreferences && (
        <OverlayDialog title="Preferences" eyebrow="Appearance" onClose={() => setShowPreferences(false)}>
          <AppearancePanel />
        </OverlayDialog>
      )}
      <ToastContainer />
    </div>
  );
}
