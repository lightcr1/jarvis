import { useNavigate } from "react-router-dom";
import { J, IconFolder, IconHome, IconMail, IconMonitor } from "../../screens/jarvis-shared";

export type WorkspaceApp = "overview" | "drive" | "communication" | "desktop";

const APPS: Record<WorkspaceApp, { label: string; sublabel: string; path: string; icon: (p: { size?: number }) => JSX.Element }> = {
  overview: { label: "Overview", sublabel: "Summary of everything", path: "/workspace/overview", icon: IconHome },
  drive: { label: "Drive", sublabel: "Files & folders", path: "/workspace/files", icon: IconFolder },
  communication: { label: "Kommunikation", sublabel: "Email & Calendar", path: "/workspace/communication", icon: IconMail },
  desktop: { label: "Desktop", sublabel: "Remote PCs", path: "/workspace/desktop", icon: IconMonitor },
};

const ORDER: WorkspaceApp[] = ["overview", "drive", "communication", "desktop"];

export function WorkspaceLauncher({ current, onClose }: { current: WorkspaceApp; onClose: () => void }) {
  const navigate = useNavigate();

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
      <div
        style={{
          position: "absolute",
          top: "calc(100% + 8px)",
          left: 0,
          width: 240,
          background: J.bg2,
          border: `1px solid ${J.border}`,
          borderRadius: 10,
          zIndex: 41,
          overflow: "hidden",
          boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
        }}
      >
        <div style={{ padding: "9px 14px 7px", fontSize: 10, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Workspace apps
        </div>
        {ORDER.map(app => {
          const isCurrent = app === current;
          const Icon = APPS[app].icon;
          return (
            <button
              key={app}
              onClick={() => {
                onClose();
                if (!isCurrent) navigate(APPS[app].path);
              }}
              style={{
                width: "100%",
                textAlign: "left",
                padding: "10px 14px",
                background: isCurrent ? J.amberGlow : "none",
                border: "none",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
              onMouseEnter={e => {
                if (!isCurrent) e.currentTarget.style.background = J.bg3;
              }}
              onMouseLeave={e => {
                if (!isCurrent) e.currentTarget.style.background = "none";
              }}
            >
              <div
                style={{
                  width: 30,
                  height: 30,
                  borderRadius: 7,
                  background: isCurrent ? J.amberDim : J.bg3,
                  border: `1px solid ${isCurrent ? J.borderAccent : J.border}`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: isCurrent ? J.amber : J.textSec,
                  flexShrink: 0,
                }}
              >
                <Icon size={14} />
              </div>
              <div>
                <div style={{ fontSize: 13, color: isCurrent ? J.amber : J.text, fontWeight: isCurrent ? 600 : 500 }}>{APPS[app].label}</div>
                <div style={{ fontSize: 11, color: J.textMuted, marginTop: 1 }}>{APPS[app].sublabel}</div>
              </div>
            </button>
          );
        })}
      </div>
    </>
  );
}

export function workspaceAppFromPath(pathname: string): WorkspaceApp {
  if (pathname.startsWith("/workspace/communication")) return "communication";
  if (pathname.startsWith("/workspace/desktop")) return "desktop";
  if (pathname.startsWith("/workspace/files")) return "drive";
  return "overview";
}
