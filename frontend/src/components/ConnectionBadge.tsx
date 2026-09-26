import { useJ } from "../screens/jarvis-shared";
import { connectionColor, connectionLevel, CONNECTION_LABEL, type ConnectionLevel } from "../shared/api/connection";

export function ConnectionBadge({ online, connected, listening = false }: {
  online: boolean;
  connected: boolean;
  listening?: boolean;
}) {
  const J = useJ();
  const level: ConnectionLevel = connectionLevel(online, connected);
  const color = connectionColor(level);
  const label = level === "live" && listening ? "Listening" : CONNECTION_LABEL[level];
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={`Connection: ${label}`}
      style={{
        display: "flex", alignItems: "center", gap: 7,
        background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 999,
        padding: "6px 10px", boxShadow: "0 8px 24px rgba(0,0,0,0.18)",
      }}
    >
      <span
        aria-hidden="true"
        data-level={level}
        style={{ width: 8, height: 8, borderRadius: "50%", background: color, boxShadow: `0 0 6px ${color}` }}
      />
      <span style={{ fontSize: 11, color: J.textSec }}>{label}</span>
    </div>
  );
}
