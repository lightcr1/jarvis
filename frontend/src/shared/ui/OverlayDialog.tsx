import React from "react";

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
  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog-card" onClick={(event) => event.stopPropagation()}>
        {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
        <h3>{title}</h3>
        {children}
        {actions ? <div className="inline-actions">{actions}</div> : null}
      </div>
    </div>
  );
}
