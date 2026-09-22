import { getStoredUser } from "../api/client";
import { J } from "../../screens/jarvis-shared";

export type AppArea = "jarvis" | "workspace" | "admin" | "monitor";

const AREA_META: Record<AppArea, { label: string; sublabel: string; href: string }> = {
  jarvis: { label: "JARVIS", sublabel: "Chat, voice, home & infra", href: "/?screen=chat" },
  workspace: { label: "Workspace", sublabel: "Files, mail, calendar, desktop", href: "/workspace" },
  admin: { label: "Admin Dashboard", sublabel: "Operator console", href: "/dashboard" },
  monitor: { label: "Agent Monitor", sublabel: "Live sessions & requests", href: "/monitor" },
};

export function AppSwitcher({
  current,
  onClose,
  placement = "below",
}: {
  current: AppArea;
  onClose: () => void;
  placement?: "below" | "right";
}) {
  // Read directly from localStorage rather than useAuth(): LoginScreen.tsx
  // writes identity via setStoredIdentity() without going through AuthProvider,
  // so its React state can be stale immediately after a same-page login (no
  // full reload) — a direct read is always current regardless of which shell
  // this is mounted under.
  const isAdmin = getStoredUser()?.role === "admin";
  const areas: AppArea[] = ["jarvis", "workspace", ...(isAdmin ? (["admin", "monitor"] as AppArea[]) : [])];
  const otherAreas = areas.filter(a => a !== current);

  const posStyle: React.CSSProperties =
    placement === "right"
      ? { position: "absolute", left: "calc(100% + 8px)", top: 0 }
      : { position: "absolute", top: "calc(100% + 8px)", left: 0 };

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
      <div
        style={{
          ...posStyle,
          width: 220,
          background: J.bg2,
          border: `1px solid ${J.border}`,
          borderRadius: 10,
          zIndex: 41,
          overflow: "hidden",
          boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
        }}
      >
        <div style={{ padding: "9px 14px 7px", fontSize: 10, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Switch area
        </div>
        {otherAreas.map(area => (
          <button
            key={area}
            onClick={() => {
              onClose();
              window.location.href = AREA_META[area].href;
            }}
            style={{ width: "100%", textAlign: "left", padding: "10px 14px", background: "none", border: "none", cursor: "pointer" }}
            onMouseEnter={e => {
              e.currentTarget.style.background = J.bg3;
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = "none";
            }}
          >
            <div style={{ fontSize: 13, color: J.text, fontWeight: 500 }}>{AREA_META[area].label}</div>
            <div style={{ fontSize: 11, color: J.textMuted, marginTop: 1 }}>{AREA_META[area].sublabel}</div>
          </button>
        ))}
      </div>
    </>
  );
}
