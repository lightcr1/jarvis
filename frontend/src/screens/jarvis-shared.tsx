import React, { useEffect, useState } from 'react';

const JDark = {
  bg0: '#0c0c0c', bg1: '#111111', bg2: '#171717', bg3: '#1e1e1e',
  bg4: '#252525', bg5: '#2c2c2c',
  border: 'rgba(255,255,255,0.08)', borderHover: 'rgba(255,255,255,0.14)',
  borderAccent: 'rgba(224,154,26,0.35)',
  amber: '#e09a1a', amberBright: '#f0ae2a',
  amberDim: 'rgba(224,154,26,0.1)', amberGlow: 'rgba(224,154,26,0.15)',
  text: '#f0f0f0', textSec: '#888888', textMuted: '#555555',
  success: '#3dba84', successDim: 'rgba(61,186,132,0.1)',
  error: '#e05555', errorDim: 'rgba(224,85,85,0.1)',
  blue: '#5294e8', blueDim: 'rgba(82,148,232,0.1)',
  warn: '#e8943a', warnDim: 'rgba(232,148,58,0.1)',
};

const JLight = {
  bg0: '#ebebeb', bg1: '#f2f2f2', bg2: '#f9f9f9', bg3: '#ffffff',
  bg4: '#e2e2e2', bg5: '#d8d8d8',
  border: 'rgba(0,0,0,0.1)', borderHover: 'rgba(0,0,0,0.18)',
  borderAccent: 'rgba(174,118,0,0.4)',
  amber: '#a87200', amberBright: '#c08800',
  amberDim: 'rgba(168,114,0,0.1)', amberGlow: 'rgba(168,114,0,0.15)',
  text: '#111111', textSec: '#555555', textMuted: '#888888',
  success: '#1f9060', successDim: 'rgba(31,144,96,0.1)',
  error: '#cc2222', errorDim: 'rgba(204,34,34,0.1)',
  blue: '#2860cc', blueDim: 'rgba(40,96,204,0.1)',
  warn: '#b05800', warnDim: 'rgba(176,88,0,0.1)',
};

export const J: typeof JDark = { ...JDark };

export const AppPrefs = { compact: false };

export function applyCompact(v: boolean) {
  AppPrefs.compact = v;
  _listeners.forEach(fn => fn());
}

const _listeners: Set<() => void> = new Set();

function hexToRgb(hex: string): [number, number, number] | null {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : null;
}

export function applyAccent(color: string) {
  const rgb = hexToRgb(color);
  if (!rgb) return;
  const [r, g, b] = rgb;
  J.amber = color;
  J.amberBright = color;
  J.amberDim = `rgba(${r},${g},${b},0.1)`;
  J.amberGlow = `rgba(${r},${g},${b},0.15)`;
  J.borderAccent = `rgba(${r},${g},${b},0.35)`;
  _listeners.forEach(fn => fn());
}

export function applyTheme(theme: 'dark' | 'light') {
  Object.assign(J, theme === 'light' ? JLight : JDark);
  document.documentElement.setAttribute('data-theme', theme);
  document.body.style.background = theme === 'light' ? JLight.bg0 : JDark.bg0;
  document.body.style.color = theme === 'light' ? JLight.text : JDark.text;
  const gs = document.getElementById('jarvis-global-styles');
  if (gs) {
    const inputBg = theme === 'light' ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)';
    const inputBorder = theme === 'light' ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.09)';
    const inputColor = theme === 'light' ? '#111111' : '#f0f0f0';
    const inputFocus = theme === 'light' ? 'rgba(168,114,0,0.4)' : 'rgba(224,154,26,0.45)';
    const inputBgFocus = theme === 'light' ? 'rgba(0,0,0,0.07)' : 'rgba(255,255,255,0.07)';
    const scrollThumb = theme === 'light' ? 'rgba(0,0,0,0.15)' : 'rgba(255,255,255,0.1)';
    const optBg = theme === 'light' ? '#f9f9f9' : '#171717';
    const placeholder = theme === 'light' ? '#888' : '#555';
    gs.textContent = gs.textContent!.replace(
      /.j-input \{[^}]+\}/s,
      `.j-input { background:${inputBg}; border:1px solid ${inputBorder}; color:${inputColor}; outline:none; transition:border-color .15s,background .15s; }`
    ).replace(
      /.j-input:focus \{[^}]+\}/s,
      `.j-input:focus { border-color:${inputFocus}; background:${inputBgFocus}; }`
    ).replace(
      /.j-input::placeholder \{[^}]+\}/s,
      `.j-input::placeholder { color:${placeholder}; }`
    ).replace(
      /::-webkit-scrollbar-thumb \{[^}]+\}/s,
      `::-webkit-scrollbar-thumb { background: ${scrollThumb}; border-radius: 2px; }`
    ).replace(
      /select\.j-input option \{[^}]+\}/s,
      `select.j-input option { background:${optBg}; }`
    );
  }
  _listeners.forEach(fn => fn());
}

export function stripMarkdown(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`[^`]+`/g, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^[-*]\s+/gm, '')
    .replace(/^\d+\.\s+/gm, '')
    .trim();
}

export function useJ(): typeof JDark {
  const [, rerender] = useState(0);
  useEffect(() => {
    const fn = () => rerender(n => n + 1);
    _listeners.add(fn);
    return () => { _listeners.delete(fn); };
  }, []);
  return J;
}

(function injectGlobalStyles() {
  if (document.getElementById('jarvis-global-styles')) return;
  const s = document.createElement('style');
  s.id = 'jarvis-global-styles';
  s.textContent = `
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Outfit', sans-serif; background: #0c0c0c; color: #f0f0f0; -webkit-font-smoothing: antialiased; }
    ::-webkit-scrollbar { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
    input, textarea, button, select { font-family: 'Outfit', sans-serif; }
    @keyframes fadeIn { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
    @keyframes slideInRight { from{transform:translateX(20px);opacity:0} to{transform:translateX(0);opacity:1} }
    @keyframes spin { to{transform:rotate(360deg)} }
    @keyframes waveBar { 0%,100%{transform:scaleY(.25)} 50%{transform:scaleY(1)} }
    .j-btn { border:none; cursor:pointer; transition:all .15s ease; font-family:'Outfit',sans-serif; display:inline-flex; align-items:center; gap:6px; }
    .j-btn:active { opacity:.8; }
    .j-input { background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.09); color:#f0f0f0; outline:none; transition:border-color .15s,background .15s; }
    .j-input:focus { border-color:rgba(224,154,26,0.45); background:rgba(255,255,255,0.07); }
    .j-input::placeholder { color:#555; }
    select.j-input option { background:#171717; }
  `;
  document.head.appendChild(s);
})();

function Ic({ size = 18, color = 'currentColor', sw = 1.5, children }: {
  size?: number; color?: string; sw?: number; children?: React.ReactNode;
}) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}

export const IconChat      = (p: { size?: number }) => <Ic {...p}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></Ic>;
export const IconMic       = (p: { size?: number }) => <Ic {...p}><rect x="9" y="2" width="6" height="11" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 19v3M8 22h8"/></Ic>;
export const IconSettings  = (p: { size?: number }) => <Ic {...p}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></Ic>;
export const IconHome      = (p: { size?: number }) => <Ic {...p}><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></Ic>;
export const IconGrid      = (p: { size?: number }) => <Ic {...p}><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></Ic>;
export const IconOrb       = (p: { size?: number }) => <Ic {...p}><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><line x1="12" y1="3" x2="12" y2="9"/><line x1="12" y1="15" x2="12" y2="21"/><line x1="3" y1="12" x2="9" y2="12"/><line x1="15" y1="12" x2="21" y2="12"/></Ic>;
export const IconUser      = (p: { size?: number }) => <Ic {...p}><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></Ic>;
export const IconSearch    = (p: { size?: number }) => <Ic {...p}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></Ic>;
export const IconPlus      = (p: { size?: number }) => <Ic {...p}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></Ic>;
export const IconX         = (p: { size?: number }) => <Ic {...p}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></Ic>;
export const IconCheck     = (p: { size?: number }) => <Ic {...p}><polyline points="20 6 9 17 4 12"/></Ic>;
export const IconSend      = (p: { size?: number }) => <Ic {...p}><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></Ic>;
export const IconAttach    = (p: { size?: number }) => <Ic {...p}><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></Ic>;
export const IconTool      = (p: { size?: number }) => <Ic {...p}><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></Ic>;
export const IconRefresh   = (p: { size?: number }) => <Ic {...p}><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></Ic>;
export const IconChevRight = (p: { size?: number }) => <Ic {...p}><polyline points="9 18 15 12 9 6"/></Ic>;
export const IconChevDown  = (p: { size?: number }) => <Ic {...p}><polyline points="6 9 12 15 18 9"/></Ic>;
export const IconLock      = (p: { size?: number }) => <Ic {...p}><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></Ic>;
export const IconPower     = (p: { size?: number }) => <Ic {...p}><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></Ic>;
export const IconDots      = (p: { size?: number }) => <Ic {...p}><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></Ic>;
export const IconServer    = (p: { size?: number }) => <Ic {...p}><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></Ic>;
export const IconBulb      = (p: { size?: number }) => <Ic {...p}><line x1="9" y1="18" x2="15" y2="18"/><line x1="10" y1="22" x2="14" y2="22"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"/></Ic>;
export const IconActivity  = (p: { size?: number }) => <Ic {...p}><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></Ic>;
export const IconMemory    = (p: { size?: number }) => <Ic {...p}><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></Ic>;
export const IconShield    = (p: { size?: number }) => <Ic {...p}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></Ic>;
export const IconCode      = (p: { size?: number }) => <Ic {...p}><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></Ic>;
export const IconTherm     = (p: { size?: number }) => <Ic {...p}><path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/></Ic>;
export const IconMenu      = (p: { size?: number }) => <Ic {...p}><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></Ic>;
export const IconCopy      = (p: { size?: number }) => <Ic {...p}><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></Ic>;
export const IconVolume    = (p: { size?: number }) => <Ic {...p}><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></Ic>;
export const IconBook      = (p: { size?: number }) => <Ic {...p}><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></Ic>;
export const IconTrash     = (p: { size?: number }) => <Ic {...p}><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></Ic>;
export const IconKey       = (p: { size?: number }) => <Ic {...p}><circle cx="7.5" cy="15.5" r="5.5"/><path d="M21 2L13 10M21 2h-5M21 2v5"/></Ic>;
export const IconSun       = (p: { size?: number }) => <Ic {...p}><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></Ic>;
export const IconMoon      = (p: { size?: number }) => <Ic {...p}><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></Ic>;
export const IconDownload  = (p: { size?: number }) => <Ic {...p}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></Ic>;

export function StatusBadge({ status, size = 'sm' }: { status?: string; size?: string }) {
  const cfg = ({
    connected:        { label: 'Connected',     color: J.success,   bg: J.successDim },
    online:           { label: 'Online',         color: J.success,   bg: J.successDim },
    active:           { label: 'Active',         color: J.success,   bg: J.successDim },
    success:          { label: 'Success',        color: J.success,   bg: J.successDim },
    error:            { label: 'Error',          color: J.error,     bg: J.errorDim   },
    failed:           { label: 'Failed',         color: J.error,     bg: J.errorDim   },
    offline:          { label: 'Offline',        color: J.error,     bg: J.errorDim   },
    running:          { label: 'Running',        color: J.blue,      bg: J.blueDim    },
    warning:          { label: 'Warning',        color: J.warn,      bg: J.warnDim    },
    local:            { label: 'Local',          color: J.amber,     bg: J.amberDim   },
    cloud:            { label: 'Cloud',          color: J.blue,      bg: J.blueDim    },
    hybrid:           { label: 'Hybrid',         color: J.warn,      bg: J.warnDim    },
    disabled:         { label: 'Disabled',       color: J.textMuted, bg: J.bg4 },
    'not configured': { label: 'Not Configured', color: J.textMuted, bg: J.bg4 },
    on:               { label: 'On',             color: J.success,   bg: J.successDim },
    off:              { label: 'Off',            color: J.textMuted, bg: J.bg4 },
  } as Record<string, { label: string; color: string; bg: string }>)[status?.toLowerCase() ?? '']
    || { label: status || '—', color: J.textSec, bg: J.bg4 };
  const pad = size === 'xs' ? '2px 7px' : '3px 9px';
  const fs  = size === 'xs' ? '10px' : '11px';
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: cfg.bg, color: cfg.color, borderRadius: 5, padding: pad, fontSize: fs, fontWeight: 500, letterSpacing: '0.01em', whiteSpace: 'nowrap' }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: cfg.color, flexShrink: 0 }} />
      {cfg.label}
    </span>
  );
}

export function MetricCard({ label, value, sublabel, icon, accent = J.amber }: {
  label: string; value: string | number; sublabel?: string; icon?: React.ReactNode; accent?: string;
}) {
  return (
    <div style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 12, padding: '16px 18px', flex: 1, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 11, color: J.textMuted, letterSpacing: '0.04em', textTransform: 'uppercase', fontWeight: 600 }}>{label}</span>
        {icon && <span style={{ color: accent, opacity: .6 }}>{icon}</span>}
      </div>
      <div style={{ fontSize: 28, fontWeight: 600, color: J.text, letterSpacing: '-0.02em', lineHeight: 1 }}>{value}</div>
      {sublabel && <div style={{ fontSize: 12, color: J.textMuted, marginTop: 5 }}>{sublabel}</div>}
    </div>
  );
}

export function Spinner({ size = 16, color = J.amber }: { size?: number; color?: string }) {
  return (
    <span style={{ width: size, height: size, border: `1.5px solid ${J.bg4}`, borderTopColor: color, borderRadius: '50%', animation: 'spin .65s linear infinite', display: 'inline-block', flexShrink: 0 }} />
  );
}

type ToastItem = { id: number; msg: string; kind: 'info' | 'success' | 'error' };
const _toastListeners = new Set<(items: ToastItem[]) => void>();
let _toastItems: ToastItem[] = [];
let _toastSeq = 0;

export function showToast(msg: string, kind: ToastItem['kind'] = 'info', duration = 2800) {
  const id = ++_toastSeq;
  _toastItems = [..._toastItems, { id, msg, kind }];
  _toastListeners.forEach(fn => fn(_toastItems));
  setTimeout(() => {
    _toastItems = _toastItems.filter(t => t.id !== id);
    _toastListeners.forEach(fn => fn(_toastItems));
  }, duration);
}

export function ToastContainer() {
  const [items, setItems] = useState<ToastItem[]>([]);
  useEffect(() => {
    const cb = (next: ToastItem[]) => setItems([...next]);
    _toastListeners.add(cb);
    return () => { _toastListeners.delete(cb); };
  }, []);
  if (!items.length) return null;
  const kindColor = { info: J.amber, success: J.success, error: J.error };
  return (
    <div style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 9999, display: 'flex', flexDirection: 'column', gap: 8, pointerEvents: 'none' }}>
      {items.map(t => (
        <div key={t.id} style={{ background: J.bg2, border: `1px solid ${kindColor[t.kind]}33`, borderLeft: `3px solid ${kindColor[t.kind]}`, borderRadius: 9, padding: '10px 16px', fontSize: 13, color: J.text, boxShadow: '0 4px 20px rgba(0,0,0,0.4)', animation: 'fadeIn .2s ease', minWidth: 200, maxWidth: 340 }}>
          {t.msg}
        </div>
      ))}
    </div>
  );
}

export function useAutoResize(ref: React.RefObject<HTMLTextAreaElement | null>, value: string) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }, [ref, value]);
}

function renderInline(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;
  while (remaining.length > 0) {
    const bold = remaining.match(/^(.*?)\*\*(.+?)\*\*/s);
    const code = remaining.match(/^(.*?)`([^`]+)`/s);
    const first = [bold, code]
      .filter(Boolean)
      .sort((a, b) => (a![1].length) - (b![1].length))[0];
    if (!first) { parts.push(remaining); break; }
    if (first[1].length > 0) parts.push(first[1]);
    if (first === bold) {
      parts.push(<strong key={key++} style={{ color: J.text, fontWeight: 600 }}>{first[2]}</strong>);
    } else {
      parts.push(<code key={key++} style={{ background: J.bg3, border: `1px solid ${J.border}`, borderRadius: 4, padding: '1px 5px', fontSize: '0.9em', fontFamily: 'monospace', color: J.amber }}>{first[2]}</code>);
    }
    remaining = remaining.slice(first[1].length + first[0].length - first[1].length);
  }
  return parts;
}

export function MarkdownText({ text, style }: { text: string; style?: React.CSSProperties }) {
  const lines = text.split('\n');
  return (
    <div style={style}>
      {lines.map((line, li) => {
        if (line.startsWith('• ') || line.startsWith('- ') || line.startsWith('* ')) {
          return (
            <div key={li} style={{ display: 'flex', gap: 8, marginBottom: 2 }}>
              <span style={{ color: J.amber, flexShrink: 0 }}>•</span>
              <span>{renderInline(line.slice(2))}</span>
            </div>
          );
        }
        if (line.trim() === '') {
          return <div key={li} style={{ height: 6 }} />;
        }
        return <div key={li} style={{ marginBottom: 1 }}>{renderInline(line)}</div>;
      })}
    </div>
  );
}
