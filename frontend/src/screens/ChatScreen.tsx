import React, { useState, useRef, useEffect } from 'react';
import {
  J, useJ, AppPrefs, stripMarkdown, StatusBadge, Spinner,
  showToast, useAutoResize,
  IconMic, IconSettings, IconPlus, IconSearch, IconSend,
  IconAttach, IconTool, IconChevDown, IconMenu, IconCopy, IconCheck, IconX,
} from './jarvis-shared';
import {
  listChatSessions, createChatSession, streamChatMessage, getChatSession,
  renameChatSession, deleteChatSession, synthesizeSpeech, getDailyBriefing,
} from '../shared/api/chat';
import type { ChatSessionListItem } from '../shared/api/chat';
import { getStoredPreferences, setStoredPreferences, getStoredUser, apiRequest } from '../shared/api/client';
import { OverlayDialog } from '../shared/ui/OverlayDialog';

type Msg = {
  id: number;
  role: 'user' | 'jarvis';
  content: string;
  time: string;
  tool?: { name: string; status: string; category: string; result: string; details?: string };
};

type SidebarGroup = { section: string; items: Array<{ id: string; title: string }> };

function groupSessions(sessions: ChatSessionListItem[]): SidebarGroup[] {
  const now = Date.now();
  const DAY = 86400000;
  const groups: SidebarGroup[] = [
    { section: 'Today',       items: [] },
    { section: 'Yesterday',   items: [] },
    { section: 'Last 7 Days', items: [] },
    { section: 'Older',       items: [] },
  ];
  for (const s of sessions) {
    const age = now - s.updated_at * 1000;
    const item = { id: s.id, title: s.title || 'New Chat' };
    if (age < DAY)         groups[0].items.push(item);
    else if (age < 2*DAY)  groups[1].items.push(item);
    else if (age < 7*DAY)  groups[2].items.push(item);
    else                   groups[3].items.push(item);
  }
  return groups.filter(g => g.items.length > 0);
}

function ToolCard({ tool }: { tool: NonNullable<Msg['tool']> }) {
  const [open, setOpen] = useState(false);
  const borderColor = ({ success: J.success, failed: J.error, running: J.blue } as Record<string, string>)[tool.status] || J.border;
  return (
    <div style={{ background: J.bg2, border: `1px solid ${J.border}`, borderLeft: `2px solid ${borderColor}`, borderRadius: 10, padding: '11px 14px', marginBottom: 8, fontSize: 13, animation: 'fadeIn .25s ease' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{ color: J.textMuted }}><IconTool size={12} /></span>
          <span style={{ fontWeight: 500, color: J.textSec, fontSize: 12 }}>{tool.name}</span>
          <span style={{ fontSize: 11, color: J.textMuted, background: J.bg3, padding: '1px 6px', borderRadius: 4 }}>{tool.category}</span>
        </div>
        <StatusBadge status={tool.status} size="xs" />
      </div>
      <div style={{ color: J.textSec, fontSize: 13, lineHeight: 1.5 }}>{tool.result}</div>
      {tool.details && (
        <>
          <button onClick={() => setOpen(v => !v)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: J.amber, fontSize: 12, marginTop: 6, display: 'flex', alignItems: 'center', gap: 4, padding: 0 }}>
            <span style={{ display: 'inline-block', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .18s' }}><IconChevDown size={12} /></span>
            {open ? 'Hide' : 'Details'}
          </button>
          {open && <pre style={{ marginTop: 7, fontFamily: 'JetBrains Mono,monospace', fontSize: 11, color: J.textSec, background: J.bg3, borderRadius: 7, padding: '9px 11px', whiteSpace: 'pre-wrap', lineHeight: 1.6, overflowX: 'auto' }}>{tool.details}</pre>}
        </>
      )}
    </div>
  );
}


function parseInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  const regex = /(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/g;
  let last = 0, m: RegExpExecArray | null;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const raw = m[0];
    if (raw.startsWith('**')) parts.push(<strong key={m.index} style={{ fontWeight: 600 }}>{raw.slice(2, -2)}</strong>);
    else if (raw.startsWith('*')) parts.push(<em key={m.index}>{raw.slice(1, -1)}</em>);
    else parts.push(<code key={m.index} style={{ fontFamily: 'JetBrains Mono,monospace', fontSize: '0.88em', background: J.bg3, padding: '1px 5px', borderRadius: 4, color: J.amber }}>{raw.slice(1, -1)}</code>);
    last = m.index + raw.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.length === 1 ? parts[0] : <React.Fragment>{parts}</React.Fragment>;
}

function MarkdownText({ text }: { text: string }) {
  const streaming = text.endsWith('▋');
  const body = streaming ? text.slice(0, -1) : text;
  const segments = body.split(/(```(?:\w+\n?)?[\s\S]*?```)/g);

  return (
    <div style={{ fontSize: 14, lineHeight: 1.7, color: J.text }}>
      {segments.map((seg, si) => {
        if (seg.startsWith('```')) {
          const inner = seg.replace(/^```\w*\n?/, '').replace(/```$/, '').trim();
          return <pre key={si} style={{ fontFamily: 'JetBrains Mono,monospace', fontSize: 12, color: J.textSec, background: J.bg3, borderRadius: 8, padding: '10px 14px', overflowX: 'auto', lineHeight: 1.6, margin: '8px 0', whiteSpace: 'pre-wrap' }}>{inner}</pre>;
        }
        const lines = seg.split('\n');
        const nodes: React.ReactNode[] = [];
        let listBuf: string[] = [];
        let listOrdered = false;

        const flushList = (key: string) => {
          if (!listBuf.length) return;
          const Tag = listOrdered ? 'ol' : 'ul';
          nodes.push(
            <Tag key={key} style={{ paddingLeft: 20, margin: '6px 0' }}>
              {listBuf.map((item, i) => <li key={i} style={{ marginBottom: 3 }}>{parseInline(item)}</li>)}
            </Tag>
          );
          listBuf = [];
        };

        lines.forEach((line, li) => {
          const ulm = line.match(/^[-*]\s+(.*)/);
          const olm = line.match(/^\d+\.\s+(.*)/);
          const hm  = line.match(/^(#{1,3})\s+(.*)/);
          if (ulm) { if (listOrdered && listBuf.length) flushList(`l${li}`); listOrdered = false; listBuf.push(ulm[1]); }
          else if (olm) { if (!listOrdered && listBuf.length) flushList(`l${li}`); listOrdered = true; listBuf.push(olm[1]); }
          else {
            flushList(`l${li}`);
            if (hm) {
              const fs = [17, 15, 14][hm[1].length - 1] ?? 14;
              nodes.push(<div key={li} style={{ fontSize: fs, fontWeight: 600, color: J.text, margin: '10px 0 3px' }}>{parseInline(hm[2])}</div>);
            } else if (line.trim()) {
              nodes.push(<div key={li} style={{ marginBottom: 3 }}>{parseInline(line)}</div>);
            } else if (nodes.length > 0) {
              nodes.push(<div key={li} style={{ height: 6 }} />);
            }
          }
        });
        flushList(`lend${si}`);
        return <React.Fragment key={si}>{nodes}</React.Fragment>;
      })}
      {streaming && <span style={{ color: J.amber, fontWeight: 300 }}>▋</span>}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  };
  return (
    <button onClick={copy} title="Copy" style={{ background: 'none', border: 'none', cursor: 'pointer', color: copied ? J.success : J.textMuted, padding: '2px 4px', borderRadius: 4, display: 'flex', alignItems: 'center', transition: 'color .15s' }}
      onMouseEnter={e => { if (!copied) e.currentTarget.style.color = J.textSec; }}
      onMouseLeave={e => { if (!copied) e.currentTarget.style.color = J.textMuted; }}>
      {copied ? <IconCheck size={12} /> : <IconCopy size={12} />}
    </button>
  );
}

function Bubble({ msg }: { msg: Msg }) {
  const isUser = msg.role === 'user';
  const compact = AppPrefs.compact;
  const [hovered, setHovered] = useState(false);
  const plainText = msg.content.replace(/▋$/, '');
  return (
    <div onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', marginBottom: compact ? 12 : 20, animation: 'fadeIn .25s ease' }}>
      {!isUser && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: compact ? 3 : 6 }}>
          <div style={{ width: compact ? 18 : 24, height: compact ? 18 : 24, borderRadius: '50%', background: J.amberDim, border: `1px solid ${J.borderAccent}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: compact ? 8 : 10, fontWeight: 700, color: J.amber, flexShrink: 0 }}>J</div>
          <span style={{ fontSize: 11, color: J.textMuted }}>Jarvis · {msg.time}</span>
          {hovered && plainText && <CopyButton text={plainText} />}
        </div>
      )}
      {isUser && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: compact ? 3 : 5 }}>
          {hovered && plainText && <CopyButton text={plainText} />}
          <span style={{ fontSize: 11, color: J.textMuted }}>You · {msg.time}</span>
        </div>
      )}
      {msg.tool && <ToolCard tool={msg.tool} />}
      {msg.content && (
        <div style={{ maxWidth: '78%', background: isUser ? J.bg3 : 'transparent', border: isUser ? `1px solid ${J.border}` : 'none', borderRadius: isUser ? '12px 12px 3px 12px' : 0, padding: isUser ? (compact ? '7px 11px' : '10px 14px') : 0 }}>
          {isUser ? <span style={{ fontSize: compact ? 13 : 14, lineHeight: compact ? 1.5 : 1.7, color: J.text }}>{msg.content}</span> : <MarkdownText text={msg.content} />}
        </div>
      )}
    </div>
  );
}

const SLASH_COMMANDS = [
  { cmd: '/status',   full: 'system status',       desc: 'Overall system health' },
  { cmd: '/disk',     full: 'disks',               desc: 'All disk usage' },
  { cmd: '/cpu',      full: 'cpu',                 desc: 'CPU load' },
  { cmd: '/memory',   full: 'memory',              desc: 'RAM usage' },
  { cmd: '/load',     full: 'load average',        desc: 'System load average' },
  { cmd: '/docker',   full: 'docker',              desc: 'Running containers' },
  { cmd: '/ports',    full: 'ports',               desc: 'Open network ports' },
  { cmd: '/ip',       full: 'ip address',          desc: 'Network addresses' },
  { cmd: '/who',      full: 'who',                 desc: 'Logged-in users' },
  { cmd: '/time',     full: 'time',                desc: 'Current time & date' },
  { cmd: '/uptime',   full: 'uptime',              desc: 'Server uptime' },
  { cmd: '/sysinfo',  full: 'sysinfo',             desc: 'Full system info' },
  { cmd: '/processes',full: 'processes',           desc: 'Top processes by CPU' },
  { cmd: '/kernel',   full: 'kernel',              desc: 'Kernel version' },
  { cmd: '/last',     full: 'last logins',         desc: 'Recent login history' },
  { cmd: '/notes',    full: 'what do you remember',desc: 'Saved notes' },
  { cmd: '/help',     full: 'help',                desc: 'All available skills' },
  { cmd: '/whoami',   full: 'whoami',              desc: 'My account info' },
  { cmd: '/uuid',     full: 'uuid',                desc: 'Generate a UUID v4' },
  { cmd: '/ts',       full: 'timestamp',           desc: 'Current Unix timestamp' },
  { cmd: '/pw',       full: 'generate password',   desc: 'Secure random password' },
  { cmd: '/briefing', full: 'briefing',            desc: 'Full system & status briefing' },
  { cmd: '/coin',     full: 'flip a coin',         desc: 'Heads or tails' },
  { cmd: '/dice',     full: 'roll a dice',         desc: 'Roll a d6' },
  { cmd: '/morse',    full: 'morse ',              desc: 'Encode text to Morse code' },
  { cmd: '/ssl',      full: 'ssl ',                desc: 'SSL certificate expiry check' },
  { cmd: '/http',     full: 'http status ',        desc: 'HTTP health check for a URL' },
];

function Composer({ onSend, sending, onStop, textareaRef }: { onSend: (v: string) => void; sending: boolean; onStop?: () => void; textareaRef?: React.RefObject<HTMLTextAreaElement> }) {
  const [val, setVal] = useState('');
  const [mode, setMode] = useState('auto');
  const [slashIdx, setSlashIdx] = useState(0);
  const internalRef = useRef<HTMLTextAreaElement>(null);
  const activeRef = textareaRef ?? internalRef;
  useAutoResize(activeRef, val);
  const send = () => { if (val.trim() && !sending) { onSend(val.trim()); setVal(''); } };

  const slashFilter = val.startsWith('/')
    ? SLASH_COMMANDS.filter(c => c.cmd.startsWith(val.toLowerCase()) || c.desc.toLowerCase().includes(val.slice(1).toLowerCase()))
    : [];
  const showSlash = slashFilter.length > 0 && !val.includes(' ');

  const pickSlash = (full: string) => { onSend(full); setVal(''); };

  return (
    <div style={{ padding: '12px 20px 18px', borderTop: `1px solid ${J.border}`, background: J.bg1, flexShrink: 0, position: 'relative' }}>
      {showSlash && (
        <div style={{ position: 'absolute', bottom: '100%', left: 20, right: 20, background: J.bg2, border: `1px solid ${J.borderAccent}`, borderRadius: 12, overflow: 'hidden', zIndex: 50, boxShadow: '0 -8px 24px rgba(0,0,0,0.35)', marginBottom: 4 }}>
          {slashFilter.map((c, i) => (
            <button key={c.cmd} onMouseDown={e => { e.preventDefault(); pickSlash(c.full); }}
              style={{ width: '100%', textAlign: 'left', background: i === slashIdx ? J.bg3 : 'none', border: 'none', padding: '9px 14px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 12, transition: 'background .08s' }}
              onMouseEnter={() => setSlashIdx(i)}>
              <span style={{ fontSize: 12, fontWeight: 600, color: J.amber, fontFamily: 'monospace', minWidth: 90 }}>{c.cmd}</span>
              <span style={{ fontSize: 12, color: J.textSec }}>{c.desc}</span>
            </button>
          ))}
        </div>
      )}
      <div style={{ background: J.bg2, border: `1px solid rgba(255,255,255,0.09)`, borderRadius: 14, overflow: 'hidden', transition: 'border-color .15s' }}
        onFocusCapture={e => { (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(224,154,26,0.35)'; }}
        onBlurCapture={e => { (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(255,255,255,0.09)'; }}>
        <textarea ref={activeRef} className="j-input" value={val} onChange={e => { setVal(e.target.value); setSlashIdx(0); }}
          onKeyDown={e => {
            if (showSlash) {
              if (e.key === 'ArrowDown') { e.preventDefault(); setSlashIdx(i => Math.min(i + 1, slashFilter.length - 1)); return; }
              if (e.key === 'ArrowUp') { e.preventDefault(); setSlashIdx(i => Math.max(i - 1, 0)); return; }
              if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) { e.preventDefault(); pickSlash(slashFilter[slashIdx].full); return; }
              if (e.key === 'Escape') { setVal(''); return; }
            }
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
          }}
          placeholder="Ask Jarvis anything… (type / for commands)"  rows={1}
          style={{ width: '100%', border: 'none', background: 'transparent', padding: '13px 16px 6px', fontSize: 14, lineHeight: 1.6, resize: 'none', overflow: 'hidden', minHeight: 46 }} />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '5px 10px 10px' }}>
          <div style={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            {[{ icon: <IconMic size={14} />, title: 'Voice' }, { icon: <IconAttach size={14} />, title: 'Attach' }].map((b, i) => (
              <button key={i} title={b.title} className="j-btn" style={{ background: 'none', color: J.textMuted, padding: '5px 6px', borderRadius: 7 }}
                onMouseEnter={e => { e.currentTarget.style.color = J.textSec; e.currentTarget.style.background = J.bg3; }}
                onMouseLeave={e => { e.currentTarget.style.color = J.textMuted; e.currentTarget.style.background = 'none'; }}>
                {b.icon}
              </button>
            ))}
            <div style={{ width: 1, height: 14, background: J.border, margin: '0 5px' }} />
            <div style={{ display: 'flex', background: J.bg3, borderRadius: 7, padding: 2, gap: 1 }}>
              {['Local', 'Cloud', 'Auto'].map(m => (
                <button key={m} onClick={() => setMode(m.toLowerCase())} style={{ background: mode === m.toLowerCase() ? J.bg4 : 'none', border: 'none', cursor: 'pointer', color: mode === m.toLowerCase() ? J.text : J.textMuted, padding: '2px 8px', borderRadius: 5, fontSize: 11, fontWeight: 500 }}>{m}</button>
              ))}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {sending ? (
              <>
                <Spinner size={14} />
                {onStop && (
                  <button onClick={onStop} title="Stop generation"
                    style={{ background: J.bg3, border: `1px solid ${J.border}`, borderRadius: 7, padding: '4px 10px', fontSize: 12, color: J.error, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5, fontWeight: 500 }}
                    onMouseEnter={e => { e.currentTarget.style.background = J.errorDim; e.currentTarget.style.borderColor = J.error; }}
                    onMouseLeave={e => { e.currentTarget.style.background = J.bg3; e.currentTarget.style.borderColor = J.border; }}>
                    <IconX size={11} /> Stop
                  </button>
                )}
              </>
            ) : (
              <span style={{ fontSize: 11, color: J.textMuted, display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 5, height: 5, borderRadius: '50%', background: J.success, display: 'inline-block' }} />
                Ready
              </span>
            )}
            <button className="j-btn" onClick={send} disabled={sending}
              style={{ background: val.trim() && !sending ? J.amber : J.bg3, color: val.trim() && !sending ? '#0c0c0c' : J.textMuted, borderRadius: 8, padding: '7px 13px', fontSize: 13, fontWeight: 600, transition: 'all .15s' }}>
              <IconSend size={13} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ChatScreen({ onNavigate }: { onNavigate: (screen: string) => void }) {
  useJ();
  const [msgs, setMsgs]       = useState<Msg[]>([]);
  const [groups, setGroups]   = useState<SidebarGroup[]>([]);
  const [active, setActive]   = useState('New Chat');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sidebar, setSidebar] = useState(true);
  const [timerCount, setTimerCount] = useState(0);
  const [billingConfirm, setBillingConfirm] = useState<{
    provider: string; model: string; estimated_cost_chf: number; balance_chf: number;
    pendingText: string;
  } | null>(null);
  const [lastRoute, setLastRoute] = useState<string>('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [hoveredSessionId, setHoveredSessionId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (document.activeElement as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        composerRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  useEffect(() => {
    listChatSessions()
      .then(data => setGroups(groupSessions(data.sessions)))
      .catch(() => {});

    const today = new Date().toISOString().slice(0, 10);
    const userId = getStoredUser()?.id ?? 'guest';
    const briefingKey = `jarvis_briefing_${userId}_${today}`;
    if (!localStorage.getItem(briefingKey)) {
      getDailyBriefing()
        .then(data => {
          const t = new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
          setMsgs(prev => [{ id: Date.now(), role: 'jarvis', content: data.text, time: t }, ...prev]);
          localStorage.setItem(briefingKey, '1');
        })
        .catch(() => {});
    }
  }, []);

  useEffect(() => {
    if (endRef.current) {
      const el = endRef.current.parentElement;
      if (el) el.scrollTop = el.scrollHeight;
    }
  }, [msgs]);

  const handleNewChat = async () => {
    try {
      const result = await createChatSession();
      setSessionId(result.session_id);
    } catch {
      setSessionId(null);
    }
    setMsgs([]);
    setActive('New Chat');
  };

  const handleSelectSession = async (item: { id: string; title: string }) => {
    setEditingId(null);
    setActive(item.title);
    setSessionId(item.id);
    try {
      const data = await getChatSession(item.id);
      const loaded: Msg[] = data.session.messages.map((m, i) => ({
        id: m.ts * 1000 + i,
        role: m.role === 'user' ? 'user' : 'jarvis',
        content: m.text,
        time: new Date(m.ts * 1000).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }),
      }));
      setMsgs(loaded);
    } catch {
      setMsgs([]);
    }
  };

  const handleStop = () => {
    if (abortRef.current) { abortRef.current.abort(); abortRef.current = null; }
  };

  const handleSend = async (text: string, _extraHeaders?: Record<string, string>) => {
    if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
    const t = new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    const userMsgId = Date.now();
    setMsgs(p => [...p, { id: userMsgId, role: 'user', content: text, time: t }]);
    setSending(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const replyId = userMsgId + 1;
    const replyTime = new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    setMsgs(p => [...p, { id: replyId, role: 'jarvis', content: '▋', time: replyTime }]);

    try {
      let accumulated = '';
      let firstToken = true;
      for await (const event of streamChatMessage(text, 'web', 'chat', sessionId, ctrl.signal)) {
        if (event.type === 'token') {
          if (firstToken) { accumulated = ''; firstToken = false; }
          accumulated += event.token;
          setMsgs(p => p.map(m => m.id === replyId ? { ...m, content: accumulated + '▋' } : m));
        } else if (event.type === 'done') {
          const final = event.reply || accumulated;
          setMsgs(p => p.map(m => m.id === replyId ? { ...m, content: final } : m));
          if ((event as Record<string, unknown>)['billing_confirmation']) {
            const bc = (event as Record<string, unknown>)['billing_confirmation'] as Record<string, unknown>;
            setBillingConfirm({
              provider: String(bc['provider'] ?? ''),
              model: String(bc['model'] ?? ''),
              estimated_cost_chf: Number(bc['estimated_cost_chf'] ?? 0),
              balance_chf: Number(bc['balance_chf'] ?? 0),
              pendingText: text,
            });
          }
          if (!sessionId && event.session_id) {
            const newSid = event.session_id;
            setSessionId(newSid);
            const autoTitle = text.slice(0, 48).trim() + (text.length > 48 ? '…' : '');
            setActive(autoTitle);
            renameChatSession(newSid, autoTitle)
              .then(() => listChatSessions().then(d => setGroups(groupSessions(d.sessions))).catch(() => {}))
              .catch(() => listChatSessions().then(d => setGroups(groupSessions(d.sessions))).catch(() => {}));
          }
          if (event.prefs_update) {
            setStoredPreferences({ ...getStoredPreferences(), ...event.prefs_update as Record<string, unknown> });
            const pu = event.prefs_update as Record<string, unknown>;
            if (pu.display_name) showToast(`Name saved: ${pu.display_name}`, 'success');
            else if (pu.location) showToast(`Location saved: ${pu.location}`, 'success');
            else if (pu.notes) showToast('Note saved', 'success');
          }
          if (event.data) {
            const route = (event.data as Record<string, unknown>)['route'] as string | undefined;
            if (route && route !== 'reminder' && route !== 'skill') setLastRoute(route);
          }
          if (event.data && (event.data as Record<string, unknown>)['route'] === 'reminder') {
            const rd = event.data as Record<string, unknown>;
            const delayMs = typeof rd['delay_ms'] === 'number' ? rd['delay_ms'] : 0;
            const label   = typeof rd['label']    === 'string' ? rd['label']    : 'Timer done.';
            if (delayMs > 0) {
              setTimerCount(c => c + 1);
              window.setTimeout(() => {
                showToast(label, 'info', 6000);
                setTimerCount(c => Math.max(0, c - 1));
              }, delayMs);
            }
          }
          if (getStoredPreferences().auto_play_voice) {
            synthesizeSpeech(stripMarkdown(final)).then(blob => {
              const url = URL.createObjectURL(blob);
              const audio = new Audio(url);
              audioRef.current = audio;
              audio.onended = () => { URL.revokeObjectURL(url); audioRef.current = null; };
              void audio.play();
            }).catch(() => {});
          }
        } else if (event.type === 'error') {
          setMsgs(p => p.map(m => m.id === replyId ? { ...m, content: `Error: ${event.detail}` } : m));
        }
      }
      // If no tokens arrived and content is still the cursor, replace with fallback
      setMsgs(p => p.map(m => m.id === replyId && m.content === '▋' ? { ...m, content: '—' } : m));
    } catch (err) {
      const isAbort = err instanceof DOMException && err.name === 'AbortError';
      if (isAbort) {
        setMsgs(p => p.map(m => m.id === replyId && (m.content === '▋' || m.content === '') ? { ...m, content: '—' } : m.id === replyId ? { ...m, content: m.content.replace(/▋$/, '') } : m));
      } else {
        setMsgs(p => p.map(m => m.id === replyId ? { ...m, content: `Error: ${(err as Error).message}` } : m));
      }
    } finally {
      abortRef.current = null;
      setSending(false);
    }
  };

  const handleRename = async (targetId: string, nextTitle: string) => {
    const clean = nextTitle.trim();
    setEditingId(null);
    if (!clean) return;
    try {
      const data = await renameChatSession(targetId, clean);
      setGroups(prev => prev.map(group => ({
        ...group,
        items: group.items.map(item => item.id === targetId ? { ...item, title: data.session.title } : item),
      })).filter(group => group.items.length > 0));
      if (sessionId === targetId) setActive(data.session.title);
    } catch {
      setEditingTitle('');
    }
  };

  const handleDeleteSession = async (e: React.MouseEvent, targetId: string) => {
    e.stopPropagation();
    try {
      await deleteChatSession(targetId);
      setGroups(prev => prev.map(group => ({
        ...group,
        items: group.items.filter(item => item.id !== targetId),
      })).filter(group => group.items.length > 0));
      if (sessionId === targetId) {
        setSessionId(null);
        setMsgs([]);
        setActive('New Chat');
      }
    } catch {
      showToast('Failed to delete chat', 'error');
    }
  };

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden', height: '100%' }}>
      {/* Sidebar */}
      {sidebar && (
        <div style={{ width: 240, flexShrink: 0, background: J.bg1, borderRight: `1px solid ${J.border}`, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ padding: '12px 10px 8px' }}>
            <button className="j-btn" onClick={() => void handleNewChat()}
              style={{ width: '100%', background: J.bg2, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 9, padding: '8px 12px', fontSize: 13, fontWeight: 500, justifyContent: 'center' }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = J.borderHover; e.currentTarget.style.color = J.text; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = J.border; e.currentTarget.style.color = J.textSec; }}>
              <IconPlus size={13} /> New Chat
            </button>
          </div>
          <div style={{ padding: '0 10px 8px' }}>
            <div style={{ position: 'relative' }}>
              <span style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: J.textMuted, pointerEvents: 'none' }}><IconSearch size={12} /></span>
              <input className="j-input" placeholder="Search…" value={search} onChange={e => setSearch(e.target.value)} style={{ width: '100%', padding: '6px 9px 6px 27px', borderRadius: 7, fontSize: 12 }} />
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '0 6px' }}>
            {(search
              ? [{ section: 'Results', items: groups.flatMap(g => g.items).filter(i => i.title.toLowerCase().includes(search.toLowerCase())) }]
              : groups
            ).map(sec => (
              <div key={sec.section} style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, padding: '2px 8px 5px' }}>{sec.section}</div>
                {sec.items.map(item => (
                  <div key={item.id}
                    style={{ position: 'relative', width: '100%', textAlign: 'left', background: active === item.title ? J.bg2 : (hoveredSessionId === item.id ? J.bg2 : 'none'), border: active === item.title ? `1px solid ${J.border}` : '1px solid transparent', borderRadius: 7, padding: '6px 9px', fontSize: 12, color: active === item.title ? J.text : J.textSec, cursor: 'pointer', marginBottom: 1, display: 'block', transition: 'all .1s' }}
                    onMouseEnter={() => setHoveredSessionId(item.id)}
                    onMouseLeave={() => setHoveredSessionId(null)}>
                    {editingId === item.id ? (
                      <input
                        autoFocus
                        className="j-input"
                        value={editingTitle}
                        onChange={e => setEditingTitle(e.target.value)}
                        onBlur={() => void handleRename(item.id, editingTitle)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') {
                            e.preventDefault();
                            void handleRename(item.id, editingTitle);
                          } else if (e.key === 'Escape') {
                            setEditingId(null);
                            setEditingTitle('');
                          }
                        }}
                        style={{ width: '100%', borderRadius: 6, padding: '3px 6px', fontSize: 12 }}
                      />
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <button
                          onClick={() => void handleSelectSession(item)}
                          onDoubleClick={() => { setEditingId(item.id); setEditingTitle(item.title); }}
                          style={{ flex: 1, textAlign: 'left', background: 'none', border: 'none', padding: 0, fontSize: 12, color: 'inherit', cursor: 'pointer', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}
                        >
                          {item.title}
                        </button>
                        {hoveredSessionId === item.id && (
                          <button
                            onClick={e => void handleDeleteSession(e, item.id)}
                            title="Delete chat"
                            style={{ flexShrink: 0, background: 'none', border: 'none', cursor: 'pointer', color: J.textMuted, padding: '1px 3px', borderRadius: 4, fontSize: 14, lineHeight: 1, display: 'flex', alignItems: 'center' }}
                            onMouseEnter={e => { e.currentTarget.style.color = J.error; e.currentTarget.style.background = J.errorDim; }}
                            onMouseLeave={e => { e.currentTarget.style.color = J.textMuted; e.currentTarget.style.background = 'none'; }}
                          >×</button>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ))}
            {groups.length === 0 && !search && (
              <div style={{ fontSize: 12, color: J.textMuted, padding: '12px 8px' }}>No conversations yet</div>
            )}
            {search && groups.flatMap(g => g.items).filter(i => i.title.toLowerCase().includes(search.toLowerCase())).length === 0 && (
              <div style={{ fontSize: 12, color: J.textMuted, padding: '12px 8px' }}>No matches</div>
            )}
          </div>
        </div>
      )}

      {/* Main */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: J.bg1 }}>
        {/* Topbar */}
        <div style={{ height: 50, borderBottom: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 18px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <button onClick={() => setSidebar(v => !v)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: J.textMuted, padding: 3, display: 'flex' }}><IconMenu size={15} /></button>
            <span style={{ fontSize: 14, fontWeight: 500, color: J.text }}>{active}</span>
            {lastRoute && (
              <StatusBadge
                status={/openrouter|anthropic|openai|gemini|mistral|deepseek/.test(lastRoute) ? 'cloud' : 'local'}
                size="xs"
              />
            )}
          </div>
          <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
            {timerCount > 0 && (
              <div title={`${timerCount} active timer${timerCount !== 1 ? 's' : ''}`}
                style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, borderRadius: 7, padding: '3px 9px', fontSize: 11, color: J.amber, display: 'flex', alignItems: 'center', gap: 5, fontWeight: 500 }}>
                ⏱ {timerCount}
              </div>
            )}
            <button onClick={() => onNavigate('orb')} className="j-btn"
              style={{ background: J.bg2, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 7, padding: '5px 11px', fontSize: 12 }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = J.borderHover; e.currentTarget.style.color = J.text; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = J.border; e.currentTarget.style.color = J.textSec; }}>
              <IconMic size={13} /> Voice
            </button>
            <button onClick={() => onNavigate('settings')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: J.textMuted, padding: 5, display: 'flex' }}><IconSettings size={14} /></button>
          </div>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px' }}>
          {msgs.length === 0 && (
            <div style={{ textAlign: 'center', paddingTop: 60, color: J.textMuted }}>
              <div style={{ width: 44, height: 44, borderRadius: 11, background: J.amberDim, border: `1px solid ${J.borderAccent}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, fontWeight: 700, color: J.amber, margin: '0 auto 16px' }}>J</div>
              <div style={{ fontSize: 16, fontWeight: 500, color: J.textSec, marginBottom: 6 }}>J.A.R.V.I.S. Online</div>
              <div style={{ fontSize: 13, marginBottom: 28 }}>All systems operational. How can I assist?</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', maxWidth: 480, margin: '0 auto' }}>
                {[
                  'Briefing',
                  'System status',
                  getStoredPreferences().location ? `Weather in ${getStoredPreferences().location}` : 'Weather forecast',
                  'Days until Christmas',
                  'Docker containers', 'Disk usage',
                  'Generate UUID', 'Flip a coin', 'Skills',
                ].map(q => (
                  <button key={q} onClick={() => void handleSend(q)}
                    style={{ background: J.bg2, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 20, padding: '6px 14px', fontSize: 12, cursor: 'pointer', transition: 'all .15s' }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = J.borderAccent; e.currentTarget.style.color = J.amber; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = J.border; e.currentTarget.style.color = J.textSec; }}>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {msgs.map(m => <Bubble key={m.id} msg={m} />)}
          <div ref={endRef} />
        </div>

        <Composer onSend={text => void handleSend(text)} sending={sending} onStop={handleStop} textareaRef={composerRef} />
      </div>

      {billingConfirm && (
        <OverlayDialog
          title="Confirm AI Request"
          eyebrow="Billing"
          onClose={() => setBillingConfirm(null)}
          actions={
            <>
              <button
                onClick={() => setBillingConfirm(null)}
                style={{ padding: '6px 14px', fontSize: 12, borderRadius: 4, cursor: 'pointer', background: 'transparent', color: J.textSec, border: `1px solid ${J.border}` }}
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  const pendingText = billingConfirm.pendingText;
                  setBillingConfirm(null);
                  void (async () => {
                    try {
                      if (sessionId) {
                        await apiRequest(`/chat/sessions/${sessionId}/pending-billing/clear`, { method: 'POST', includeUser: true }).catch(() => {});
                      }
                      void handleSend(pendingText, { 'X-Jarvis-Confirm': 'billing' });
                    } catch {
                      showToast('Failed to confirm request.', 'error');
                    }
                  })();
                }}
                style={{ padding: '6px 16px', fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: 'pointer', background: J.amber, color: J.bg0, border: 'none' }}
              >
                Confirm
              </button>
            </>
          }
        >
          <p style={{ fontSize: 13, color: J.textSec, lineHeight: 1.6 }}>
            This will use <strong style={{ color: J.text }}>{billingConfirm.model}</strong>{' '}
            via <strong style={{ color: J.text }}>{billingConfirm.provider}</strong>{' '}
            (~CHF {billingConfirm.estimated_cost_chf.toFixed(4)}).{' '}
            Your balance: <strong style={{ color: J.amber }}>CHF {billingConfirm.balance_chf.toFixed(4)}</strong>.
          </p>
        </OverlayDialog>
      )}
    </div>
  );
}
