import React, { useEffect, useRef } from "react";
import { J } from "../../screens/jarvis-shared";

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export function OverlayDialog({
  title,
  eyebrow,
  onClose,
  children,
  actions,
}: {
  title: string;
  eyebrow?: string;
  onClose: () => void;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    if (panel) {
      const first = panel.querySelectorAll<HTMLElement>(FOCUSABLE)[0];
      first?.focus();
    }

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key !== "Tab" || !panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="overlay-title"
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 200,
        background: "rgba(0,0,0,0.6)", display: "flex",
        alignItems: "center", justifyContent: "center",
        backdropFilter: "blur(2px)",
      }}
    >
      <div
        ref={panelRef}
        onClick={e => e.stopPropagation()}
        style={{
          background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 10,
          padding: "22px 24px", minWidth: 340, maxWidth: 540, width: "100%",
          boxShadow: "0 16px 48px rgba(0,0,0,0.45)",
        }}
      >
        {eyebrow && (
          <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
            {eyebrow}
          </div>
        )}
        <h3 id="overlay-title" style={{ margin: "0 0 16px", fontSize: 16, fontWeight: 600, color: J.text }}>{title}</h3>
        {children}
        {actions && (
          <div style={{ display: "flex", gap: 8, marginTop: 18, justifyContent: "flex-end" }}>
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}
