import React from "react";

export function SidebarSection({
  title,
  open,
  onToggle,
  children,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="sidebar-section">
      <button className="sidebar-group-toggle" onClick={onToggle} aria-expanded={open}>
        <span className="sidebar-section-title">{title}</span>
        <span className="sidebar-group-caret">{open ? "−" : "+"}</span>
      </button>
      {open ? children : null}
    </div>
  );
}
