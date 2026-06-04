import { useState, useMemo, useEffect } from 'react';
import {
  J, useJ, IconSearch, IconCode, IconServer, IconShield, IconActivity,
  IconMemory, IconBulb, IconSettings, IconMic, IconKey,
} from './jarvis-shared';
import { getStoredUser } from '../shared/api/client';
import { getRagStatus, RagStatus } from '../shared/api/chat';
import { fetchHomeAssistantHealth, HomeAssistantHealth } from '../shared/api/homeAssistant';

type Perm = 'any' | 'write' | 'admin';

type IntegrationState = 'loading' | 'active' | 'inactive' | 'unknown';

interface IntegrationStatuses {
  rag: IntegrationState;
  homeAssistant: IntegrationState;
}

interface Skill {
  cmd: string;
  desc: string;
  perm: Perm;
  example?: string;
}

interface SkillCat {
  id: string;
  name: string;
  Icon: (p: { size?: number }) => JSX.Element;
  skills: Skill[];
}

const SKILL_CATS: SkillCat[] = [
  {
    id: 'system', name: 'System & Server', Icon: IconServer,
    skills: [
      { cmd: 'status / health', desc: 'Overall system health check', perm: 'any' },
      { cmd: 'briefing', desc: 'Full status report — time, load, RAM, disk, notes', perm: 'any' },
      { cmd: 'cpu', desc: 'CPU usage and load average', perm: 'any' },
      { cmd: 'memory / ram', desc: 'RAM usage breakdown', perm: 'any' },
      { cmd: 'disk / disks', desc: 'Disk usage for all mount points', perm: 'any' },
      { cmd: 'uptime', desc: 'Server uptime', perm: 'any' },
      { cmd: 'sysinfo', desc: 'Full system info: hostname, OS, CPU, RAM, disk', perm: 'any' },
      { cmd: 'processes / top', desc: 'Top processes by CPU', perm: 'any' },
      { cmd: 'top memory', desc: 'Top processes by RAM usage', perm: 'any' },
      { cmd: 'docker', desc: 'Running Docker containers', perm: 'any' },
      { cmd: 'docker stats', desc: 'Container CPU/RAM usage', perm: 'any' },
      { cmd: 'who', desc: 'Currently logged-in users', perm: 'any' },
      { cmd: 'last', desc: 'Recent login history', perm: 'any' },
      { cmd: 'kernel', desc: 'Kernel version', perm: 'any' },
      { cmd: 'cpu temperature', desc: 'CPU thermal sensor readings', perm: 'any' },
      { cmd: 'battery / charge', desc: 'Battery level and charge status', perm: 'any' },
      { cmd: 'check updates', desc: 'Available package upgrades', perm: 'any' },
      { cmd: 'status <service>', desc: 'Check a specific service status', perm: 'any', example: 'status nginx' },
      { cmd: 'logs <service>', desc: 'View recent service logs', perm: 'any', example: 'logs nginx' },
      { cmd: 'restart <service>', desc: 'Restart a system service', perm: 'write', example: 'restart nginx' },
      { cmd: 'start <service>', desc: 'Start a system service', perm: 'write', example: 'start redis' },
      { cmd: 'stop <service>', desc: 'Stop a system service', perm: 'write', example: 'stop redis' },
      { cmd: 'shutdown [in N min]', desc: 'Schedule system shutdown', perm: 'admin', example: 'shutdown in 10 minutes' },
      { cmd: 'reboot', desc: 'Reboot the server', perm: 'admin' },
      { cmd: 'cancel shutdown', desc: 'Abort a pending shutdown', perm: 'admin' },
    ],
  },
  {
    id: 'network', name: 'Network & Connectivity', Icon: IconActivity,
    skills: [
      { cmd: 'ip address', desc: 'Local network addresses and interfaces', perm: 'any' },
      { cmd: 'ports / open ports', desc: 'Listening network ports', perm: 'any' },
      { cmd: 'ping <host>', desc: 'Network latency check with quality rating', perm: 'any', example: 'ping google.com' },
      { cmd: 'dns <host>', desc: 'Resolve hostname to IP address', perm: 'any', example: 'dns github.com' },
      { cmd: 'public ip', desc: 'Your external WAN IP with location info', perm: 'any' },
      { cmd: 'http status <url>', desc: 'HTTP health check — response code and latency', perm: 'any', example: 'http status https://example.com' },
      { cmd: 'ssl <domain>', desc: 'SSL certificate expiry check', perm: 'any', example: 'ssl github.com' },
    ],
  },
  {
    id: 'info', name: 'Information & Search', Icon: IconSearch,
    skills: [
      { cmd: 'weather [in <city>]', desc: 'Current weather + 3-day forecast', perm: 'any', example: 'weather in Munich' },
      { cmd: 'news / headlines', desc: 'Top BBC World News headlines', perm: 'any' },
      { cmd: 'wikipedia <topic>', desc: 'Wikipedia article summary', perm: 'any', example: 'wikipedia quantum computing' },
      { cmd: 'who is <person>', desc: 'Wikipedia lookup for a person or concept', perm: 'any', example: 'who is Nikola Tesla' },
      { cmd: 'define <word>', desc: 'Dictionary definition with phonetics and examples', perm: 'any', example: 'define serendipity' },
      { cmd: 'time [in <city>]', desc: 'Current time, optionally in another timezone', perm: 'any', example: 'time in Tokyo' },
      { cmd: 'sunrise / sunset', desc: 'Sunrise and sunset times for your saved location', perm: 'any' },
      { cmd: 'days until <event>', desc: 'Countdown to a date or holiday', perm: 'any', example: 'days until Christmas' },
      { cmd: 'days since <date>', desc: 'How long ago a date was', perm: 'any', example: 'days since January 1' },
    ],
  },
  {
    id: 'math', name: 'Math & Utilities', Icon: IconCode,
    skills: [
      { cmd: 'calculate <expr>', desc: 'Evaluate a math expression', perm: 'any', example: 'calculate 15% of 340' },
      { cmd: 'convert <N> <unit> to <unit>', desc: 'Unit conversion', perm: 'any', example: 'convert 100 km to miles' },
      { cmd: '<N> <currency> to <currency>', desc: 'Currency conversion using ECB rates', perm: 'any', example: '100 USD to EUR' },
      { cmd: 'random number [between X and Y]', desc: 'Random integer', perm: 'any', example: 'random number between 1 and 100' },
      { cmd: 'uuid', desc: 'Generate a UUID v4', perm: 'any' },
      { cmd: 'timestamp', desc: 'Current Unix timestamp', perm: 'any' },
      { cmd: 'generate password [length]', desc: 'Cryptographically secure random password', perm: 'any', example: 'generate password 24' },
      { cmd: 'sha256 / md5 <text>', desc: 'Hash a string', perm: 'any', example: 'sha256 hello world' },
      { cmd: 'base64 encode <text>', desc: 'Base64 encoding', perm: 'any', example: 'base64 encode hello' },
      { cmd: 'base64 decode <text>', desc: 'Base64 decoding', perm: 'any', example: 'base64 decode aGVsbG8=' },
      { cmd: 'hex to rgb #rrggbb', desc: 'Hex color to RGB', perm: 'any', example: 'hex to rgb #e09a1a' },
      { cmd: 'rgb to hex <r> <g> <b>', desc: 'RGB to hex color', perm: 'any' },
      { cmd: 'is <N> prime', desc: 'Prime number check', perm: 'any', example: 'is 127 prime' },
      { cmd: 'factorial <N>', desc: 'Factorial (up to 20)', perm: 'any', example: 'factorial 10' },
      { cmd: 'fibonacci <N>', desc: 'First N Fibonacci numbers', perm: 'any' },
      { cmd: 'sort <n1> <n2> ...', desc: 'Sort a list of numbers', perm: 'any' },
      { cmd: 'average <n1> <n2> ...', desc: 'Mean of a list of numbers', perm: 'any' },
      { cmd: 'word count <text>', desc: 'Count words and characters', perm: 'any' },
      { cmd: 'url encode <text>', desc: 'URL-encode a string', perm: 'any' },
      { cmd: 'morse <text>', desc: 'Encode text to Morse code', perm: 'any' },
      { cmd: 'morse decode <...>', desc: 'Decode Morse code', perm: 'any' },
      { cmd: 'to roman <N>', desc: 'Convert to Roman numerals', perm: 'any' },
      { cmd: 'ascii <char>', desc: 'ASCII character lookup', perm: 'any' },
      { cmd: 'json format <json>', desc: 'Pretty-print and validate JSON', perm: 'any', example: 'json format {"a":1}' },
      { cmd: 'json minify <json>', desc: 'Compact / minify JSON — removes all whitespace', perm: 'any', example: 'json minify {"a": 1, "b": 2}' },
      { cmd: 'json validate <json>', desc: 'Check if JSON is valid', perm: 'any' },
      { cmd: 'upper / lower / title <text>', desc: 'Convert text case (UPPER, lower, Title Case)', perm: 'any', example: 'upper hello world' },
      { cmd: 'snake / camel / pascal / kebab case <text>', desc: 'Convert to snake_case, camelCase, PascalCase, or kebab-case', perm: 'any', example: 'camel case hello world' },
      { cmd: 'screaming snake <text>', desc: 'Convert to SCREAMING_SNAKE_CASE', perm: 'any', example: 'screaming snake hello world' },
      { cmd: 'jwt decode <token>', desc: 'Inspect JWT header and payload (no verification)', perm: 'any' },
      { cmd: 'yaml format <yaml>', desc: 'Pretty-print and validate YAML', perm: 'any', example: 'yaml format name: alice\nage: 30' },
      { cmd: 'yaml validate <yaml>', desc: 'Check if YAML is valid', perm: 'any' },
      { cmd: 'regex test /<pattern>/[flags] against <text>', desc: 'Test a regex — shows all matches with positions', perm: 'any', example: 'regex test /\\d+/g against foo 123 bar 456' },
      { cmd: 'cron explain <expression>', desc: 'Decode a 5- or 6-field cron schedule to plain English', perm: 'any', example: 'cron explain 30 8 * * 1-5' },
      { cmd: 'diff <text_a> | <text_b>', desc: 'Unified diff between two text snippets', perm: 'any', example: 'diff hello world | hello everyone' },
      { cmd: 'port check <host> <port>', desc: 'Test TCP reachability of a host and port', perm: 'any', example: 'port check example.com 443' },
      { cmd: 'generate secret [<bytes>]', desc: 'Generate a cryptographically secure hex secret for API keys, JWT secrets, etc.', perm: 'any', example: 'generate secret 32' },
    ],
  },
  {
    id: 'memory', name: 'Memory & Personalization', Icon: IconMemory,
    skills: [
      { cmd: "remember that <text>", desc: 'Save a personal note — persists across sessions', perm: 'any', example: 'remember that the server PIN is 1234' },
      { cmd: "what do you remember", desc: 'List all your saved notes', perm: 'any' },
      { cmd: "forget <keyword>", desc: 'Delete notes matching a keyword', perm: 'any' },
      { cmd: "I'm in <city>", desc: 'Save your location (used for weather, sunrise)', perm: 'any', example: "I'm in Berlin" },
      { cmd: "my name is <name>", desc: 'Set your display name shown in the interface', perm: 'any' },
    ],
  },
  {
    id: 'fun', name: 'Fun & Creative', Icon: IconBulb,
    skills: [
      { cmd: 'joke / tell me a joke', desc: 'Random dad joke from icanhazdadjoke.com', perm: 'any' },
      { cmd: 'flip a coin', desc: 'Heads or tails', perm: 'any' },
      { cmd: 'roll [N]d[S]', desc: 'Dice roller — e.g. 2d6, 1d20', perm: 'any', example: 'roll 2d6' },
      { cmd: 'timer for <N> minutes', desc: 'Countdown timer with browser notification', perm: 'any', example: 'timer for 25 minutes' },
      { cmd: 'remind me in <N> min to <task>', desc: 'Timed reminder', perm: 'any', example: 'remind me in 10 minutes to check the oven' },
    ],
  },
  {
    id: 'integrations', name: 'Integrations', Icon: IconSettings,
    skills: [
      { cmd: 'pve vm status <host> <node> <id>', desc: 'Proxmox VM status', perm: 'any', example: 'pve vm status pve1 node1 100' },
      { cmd: 'pve lxc status <host> <node> <id>', desc: 'Proxmox LXC container status', perm: 'any' },
      { cmd: 'pve start vm <host> <node> <id>', desc: 'Start a Proxmox VM', perm: 'write' },
      { cmd: 'pve stop vm <host> <node> <id>', desc: 'Stop a Proxmox VM', perm: 'write' },
      { cmd: 'pve restart vm <host> <node> <id>', desc: 'Reboot a Proxmox VM', perm: 'write' },
      { cmd: 'pve start lxc <host> <node> <id>', desc: 'Start a Proxmox LXC', perm: 'write' },
      { cmd: 'pve stop lxc <host> <node> <id>', desc: 'Stop a Proxmox LXC', perm: 'write' },
      { cmd: 'pve restart lxc <host> <node> <id>', desc: 'Reboot a Proxmox LXC', perm: 'write' },
    ],
  },
];

function permBadgeStyle(perm: Perm): { label: string; color: string; bg: string } {
  if (perm === 'write') return { label: 'Write', color: J.amber, bg: J.amberDim };
  if (perm === 'admin') return { label: 'Admin', color: J.error, bg: J.errorDim };
  return { label: 'Any user', color: J.success, bg: J.successDim };
}

function PermBadge({ perm }: { perm: Perm }) {
  const b = permBadgeStyle(perm);
  return (
    <span style={{ fontSize: 10, fontWeight: 600, color: b.color, background: b.bg, padding: '2px 7px', borderRadius: 4, whiteSpace: 'nowrap' }}>
      {b.label}
    </span>
  );
}

function IntegrationBadge({ state }: { state: IntegrationState }) {
  if (state === 'loading') {
    return <span style={{ fontSize: 10, fontWeight: 600, color: J.textMuted, background: J.bg4, border: `1px solid ${J.border}`, padding: '2px 8px', borderRadius: 4 }}>checking…</span>;
  }
  if (state === 'active') {
    return <span style={{ fontSize: 10, fontWeight: 600, color: J.success, background: J.successDim, padding: '2px 8px', borderRadius: 4 }}>active</span>;
  }
  if (state === 'inactive') {
    return <span style={{ fontSize: 10, fontWeight: 600, color: J.error, background: J.errorDim, padding: '2px 8px', borderRadius: 4 }}>not configured</span>;
  }
  return <span style={{ fontSize: 10, fontWeight: 600, color: J.textMuted, background: J.bg4, border: `1px solid ${J.border}`, padding: '2px 8px', borderRadius: 4 }}>unknown</span>;
}

function CodeBox({ children }: { children: string }) {
  return (
    <pre style={{ background: J.bg3, border: `1px solid ${J.border}`, borderRadius: 8, padding: '12px 16px', fontSize: 12, fontFamily: 'JetBrains Mono,monospace', color: J.textSec, overflowX: 'auto', lineHeight: 1.7, margin: '10px 0' }}>
      {children}
    </pre>
  );
}

function H2({ children }: { children: React.ReactNode }) {
  return <h2 style={{ fontSize: 18, fontWeight: 600, color: J.text, marginBottom: 6, marginTop: 32, letterSpacing: '-0.01em' }}>{children}</h2>;
}

function H3({ children }: { children: React.ReactNode }) {
  return <h3 style={{ fontSize: 14, fontWeight: 600, color: J.text, marginBottom: 10, marginTop: 22 }}>{children}</h3>;
}

function P({ children }: { children: React.ReactNode }) {
  return <p style={{ fontSize: 13, color: J.textSec, lineHeight: 1.7, marginBottom: 10 }}>{children}</p>;
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, borderRadius: 8, padding: '10px 14px', fontSize: 12, color: J.textSec, lineHeight: 1.6, margin: '10px 0' }}>
      <span style={{ color: J.amber, fontWeight: 600 }}>Note: </span>{children}
    </div>
  );
}

function Tag({ children }: { children: string }) {
  return <code style={{ fontFamily: 'JetBrains Mono,monospace', fontSize: '0.88em', background: J.bg3, border: `1px solid ${J.border}`, padding: '1px 6px', borderRadius: 4, color: J.amber }}>{children}</code>;
}

// ── Section renderers ─────────────────────────────────────────────────────────

function OverviewSection() {
  return (
    <>
      <div style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 12, padding: '22px 24px', marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 14 }}>
          <div style={{ width: 44, height: 44, borderRadius: 11, background: J.amberDim, border: `1px solid ${J.borderAccent}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, fontWeight: 700, color: J.amber }}>J</div>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: J.text, letterSpacing: '-0.01em' }}>J.A.R.V.I.S.</div>
            <div style={{ fontSize: 12, color: J.textMuted }}>Just A Rather Very Intelligent System</div>
          </div>
        </div>
        <P>JARVIS is a privacy-first, locally-running AI assistant. All conversations, preferences, and processing happen on your own hardware — nothing leaves your network unless a skill explicitly calls an external API (weather, news, currency rates, etc.).</P>
        <P>Built on FastAPI + React, JARVIS routes requests through a fast skill engine first and falls back to a local or cloud LLM for open-ended queries.</P>
      </div>

      <H2>Key Features</H2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(220px,1fr))', gap: 12, marginBottom: 24 }}>
        {[
          { icon: <IconMic size={15} />, title: 'Voice Interface', desc: 'Wake word detection, speech-to-text, neural TTS with multiple voices' },
          { icon: <IconCode size={15} />, title: '50+ Skills', desc: 'System monitoring, calculations, web lookups, timers, and more' },
          { icon: <IconSettings size={15} />, title: 'Integrations', desc: 'Proxmox, Home Assistant, GitHub RAG, WikiJS RAG' },
          { icon: <IconShield size={15} />, title: 'RBAC & Audit', desc: 'Role-based access control, audit log, emergency stop' },
          { icon: <IconMemory size={15} />, title: 'Memory', desc: 'Persistent notes, location, display name — synced server-side' },
          { icon: <IconActivity size={15} />, title: 'Live Metrics', desc: 'CPU, RAM, disk polling in the chat header and admin dashboard' },
        ].map(f => (
          <div key={f.title} style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ color: J.amber }}>{f.icon}</span>
              <span style={{ fontSize: 13, fontWeight: 600, color: J.text }}>{f.title}</span>
            </div>
            <div style={{ fontSize: 12, color: J.textMuted, lineHeight: 1.5 }}>{f.desc}</div>
          </div>
        ))}
      </div>

      <H2>Architecture</H2>
      <P>The backend is a single <Tag>FastAPI</Tag> app serving both the API and the React SPA from <Tag>/opt/jarvis</Tag>. Skill routing happens in <Tag>assistant_domain.py</Tag> before the LLM is called — keeping responses fast and deterministic for known commands.</P>
      <CodeBox>{`/opt/jarvis/
├── jarvis/               # Python backend (FastAPI)
│   ├── assistant_domain.py   # skill engine (50+ skills)
│   ├── api_auth_chat.py      # chat + auth API routes
│   ├── audio_services.py     # TTS / STT providers
│   └── ...
└── frontend/dist/        # built React SPA`}</CodeBox>
    </>
  );
}

function GettingStartedSection() {
  return (
    <>
      <H2>Getting Started</H2>
      <H3>1. Log in</H3>
      <P>Enter your username and password on the login screen. Credentials are stored only in the local session — they never leave your network.</P>

      <H3>2. Send your first message</H3>
      <P>Click the Chat tab and type anything. Good first commands:</P>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, margin: '8px 0 16px' }}>
        {['briefing', 'cpu', 'what is the weather', 'help'].map(q => (
          <code key={q} style={{ background: J.bg3, border: `1px solid ${J.border}`, borderRadius: 6, padding: '4px 10px', fontSize: 12, color: J.amber, fontFamily: 'JetBrains Mono,monospace' }}>{q}</code>
        ))}
      </div>

      <H3>3. Use slash commands</H3>
      <P>Type <Tag>/</Tag> in the chat composer to see all available slash commands with descriptions. Press <Tag>Tab</Tag> or <Tag>Enter</Tag> to select one.</P>

      <H3>4. Save your preferences</H3>
      <P>Go to Settings to choose your voice, theme, accent color, and save your location for weather lookups.</P>

      <H3>5. Try the voice interface</H3>
      <P>Open the Voice screen (or click Voice in the chat header). Hold the mic button to speak, or enable wake word detection in Settings → Voice.</P>

      <Note>The greeting overlay plays every time you open or log in to JARVIS. Click anywhere to dismiss it.</Note>

      <H2>Keyboard Shortcuts</H2>
      <div style={{ border: `1px solid ${J.border}`, borderRadius: 10, overflow: 'hidden', marginTop: 8 }}>
        {[
          { keys: ['Ctrl', 'K'], desc: 'Focus chat input from anywhere' },
          { keys: ['/'], desc: 'Focus chat input (type commands)' },
          { keys: ['?'], desc: 'Open keyboard shortcut overlay' },
          { keys: ['Enter'], desc: 'Send message' },
          { keys: ['Shift', 'Enter'], desc: 'New line in composer' },
          { keys: ['↑'], desc: 'Recall last sent message' },
          { keys: ['↓'], desc: 'Next message in history' },
          { keys: ['Tab'], desc: 'Accept highlighted slash command' },
          { keys: ['Esc'], desc: 'Close slash command menu / clear input' },
        ].map(({ keys, desc }, i) => (
          <div key={desc} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 14px', borderBottom: i < 8 ? `1px solid ${J.border}` : 'none', background: i % 2 === 0 ? 'transparent' : J.bg2 }}>
            <span style={{ fontSize: 13, color: J.textSec }}>{desc}</span>
            <div style={{ display: 'flex', gap: 4 }}>
              {keys.map(k => <kbd key={k} style={{ fontFamily: 'JetBrains Mono,monospace', fontSize: 11, color: J.text, background: J.bg4, border: `1px solid ${J.border}`, borderRadius: 4, padding: '2px 7px' }}>{k}</kbd>)}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function SkillsSection({ search, integrations }: { search: string; integrations: IntegrationStatuses }) {
  const q = search.toLowerCase().trim();
  const filtered = useMemo(() => {
    if (!q) return SKILL_CATS;
    return SKILL_CATS.map(cat => ({
      ...cat,
      skills: cat.skills.filter(s =>
        s.cmd.toLowerCase().includes(q) || s.desc.toLowerCase().includes(q) || (s.example?.toLowerCase().includes(q) ?? false)
      ),
    })).filter(cat => cat.skills.length > 0);
  }, [q]);

  return (
    <>
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 16, marginBottom: 10, flexWrap: 'wrap' }}>
          {(['any', 'write', 'admin'] as Perm[]).map(p => (
            <div key={p} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: J.textSec }}>
              <PermBadge perm={p} />
              {p === 'any' ? '— Any logged-in user' : p === 'write' ? '— Requires write group' : '— Admin only'}
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 4 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: J.textSec }}>
            <span>RAG / Knowledge Base:</span>
            <IntegrationBadge state={integrations.rag} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: J.textSec }}>
            <span>Home Assistant:</span>
            <IntegrationBadge state={integrations.homeAssistant} />
          </div>
        </div>
      </div>
      {filtered.length === 0 && (
        <div style={{ fontSize: 13, color: J.textMuted, padding: '24px 0' }}>No skills match "{search}"</div>
      )}
      {filtered.map(cat => (
        <div key={cat.id} style={{ marginBottom: 28 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ color: J.amber }}><cat.Icon size={14} /></span>
            <span style={{ fontSize: 13, fontWeight: 600, color: J.text, letterSpacing: '0.01em' }}>{cat.name}</span>
            <span style={{ fontSize: 11, color: J.textMuted }}>({cat.skills.length})</span>
          </div>
          <div style={{ border: `1px solid ${J.border}`, borderRadius: 10, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', background: J.bg3, padding: '6px 12px', borderBottom: `1px solid ${J.border}` }}>
              <span style={{ fontSize: 10, color: J.textMuted, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>Command</span>
              <span style={{ fontSize: 10, color: J.textMuted, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>Description</span>
              <span style={{ fontSize: 10, color: J.textMuted, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>Access</span>
            </div>
            {cat.skills.map((s, i) => (
              <div key={s.cmd} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', padding: '8px 12px', borderBottom: i < cat.skills.length - 1 ? `1px solid ${J.border}` : 'none', background: i % 2 === 1 ? J.bg2 : 'transparent', alignItems: 'center', gap: 12 }}>
                <div>
                  <code style={{ fontSize: 11, color: J.amber, fontFamily: 'JetBrains Mono,monospace', display: 'block', marginBottom: s.example ? 2 : 0 }}>{s.cmd}</code>
                  {s.example && <span style={{ fontSize: 10, color: J.textMuted, fontFamily: 'JetBrains Mono,monospace' }}>e.g. {s.example}</span>}
                </div>
                <span style={{ fontSize: 12, color: J.textSec, lineHeight: 1.4 }}>{s.desc}</span>
                <PermBadge perm={s.perm} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </>
  );
}

function ProxmoxSection() {
  return (
    <>
      <H2>Proxmox Integration</H2>
      <P>JARVIS can monitor and control Proxmox VMs and LXC containers. Once configured, the Proxmox screen becomes fully functional and skills like "pve vm status" work in chat.</P>

      <H3>Required Environment Variables</H3>
      <P>Add these to your <Tag>/opt/jarvis/.env</Tag> file and restart JARVIS:</P>
      <CodeBox>{`JARVIS_PROXMOX_HOST=proxmox.lan        # hostname or IP
JARVIS_PROXMOX_USER=root@pam           # Proxmox user
JARVIS_PROXMOX_TOKEN_ID=jarvis         # API token name
JARVIS_PROXMOX_TOKEN_SECRET=xxxxxxxx   # API token secret
JARVIS_PROXMOX_VERIFY_SSL=false        # set true in production`}</CodeBox>

      <H3>How to Generate an API Token</H3>
      <P>1. Log in to your Proxmox web UI and go to <strong>Datacenter → Permissions → API Tokens</strong></P>
      <P>2. Click <strong>Add</strong>, select your user, give the token a name (e.g. <Tag>jarvis</Tag>)</P>
      <P>3. Uncheck "Privilege Separation" unless you have fine-grained permission requirements</P>
      <P>4. Copy the <strong>Token ID</strong> and <strong>Secret</strong> into your env file</P>

      <H3>Multiple Proxmox Hosts</H3>
      <P>To connect multiple Proxmox clusters, use indexed env vars:</P>
      <CodeBox>{`JARVIS_PROXMOX_HOST_0=pve1.lan
JARVIS_PROXMOX_USER_0=root@pam
JARVIS_PROXMOX_TOKEN_ID_0=jarvis
JARVIS_PROXMOX_TOKEN_SECRET_0=xxxxxxxx

JARVIS_PROXMOX_HOST_1=pve2.lan
JARVIS_PROXMOX_USER_1=root@pam
JARVIS_PROXMOX_TOKEN_ID_1=jarvis
JARVIS_PROXMOX_TOKEN_SECRET_1=yyyyyyyy`}</CodeBox>

      <H3>Chat Skills Enabled</H3>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 6 }}>
        {['pve vm status', 'pve lxc status', 'pve start vm', 'pve stop vm', 'pve restart vm', 'pve start lxc', 'pve stop lxc', 'pve restart lxc'].map(s => (
          <code key={s} style={{ background: J.bg3, border: `1px solid ${J.border}`, borderRadius: 6, padding: '4px 10px', fontSize: 11, color: J.amber, fontFamily: 'JetBrains Mono,monospace' }}>{s}</code>
        ))}
      </div>
    </>
  );
}

function HomeAssistantSection({ status }: { status: IntegrationState }) {
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600, color: J.text, margin: 0, letterSpacing: '-0.01em' }}>Home Assistant Integration</h2>
        <IntegrationBadge state={status} />
      </div>
      {status === 'inactive' && (
        <div style={{ background: J.warnDim, border: `1px solid ${J.warn}30`, borderRadius: 8, padding: '10px 14px', fontSize: 12, color: J.textSec, lineHeight: 1.6, marginBottom: 12 }}>
          <span style={{ color: J.warn, fontWeight: 600 }}>Not configured: </span>
          Home Assistant is not connected. Set <code style={{ fontFamily: 'JetBrains Mono,monospace', color: J.amber }}>JARVIS_HA_BASE_URL</code> and <code style={{ fontFamily: 'JetBrains Mono,monospace', color: J.amber }}>JARVIS_HA_TOKEN</code> to enable HA skills.
        </div>
      )}
      <P>JARVIS connects to Home Assistant to show device states, control lights, switches, and climate devices, and trigger automations — all from chat or the Home screen.</P>

      <H3>Required Environment Variables</H3>
      <CodeBox>{`JARVIS_HA_BASE_URL=http://homeassistant.local:8123
JARVIS_HA_TOKEN=eyJhbGci...  # long-lived access token`}</CodeBox>

      <H3>How to Get a Long-Lived Access Token</H3>
      <P>1. Open Home Assistant and click your <strong>profile picture</strong> (bottom left)</P>
      <P>2. Scroll to the bottom of the profile page and find <strong>Long-Lived Access Tokens</strong></P>
      <P>3. Click <strong>Create Token</strong>, give it a name (e.g. <Tag>jarvis</Tag>)</P>
      <P>4. Copy the token immediately — it will not be shown again</P>
      <P>5. Paste it as <Tag>JARVIS_HA_TOKEN</Tag> in your env file</P>

      <Note>The token gives JARVIS full HA access. Consider creating a dedicated HA user with limited permissions if you prefer.</Note>

      <H3>Features Enabled</H3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(200px,1fr))', gap: 10, marginTop: 8 }}>
        {[
          ['Device overview', 'All entities grouped by area'],
          ['Toggle lights', 'Turn on/off any light'],
          ['Climate control', 'Set thermostat modes'],
          ['Automation triggers', 'Run any automation via chat'],
          ['Live state updates', 'Real-time entity state polling'],
          ['Device drawer', 'Click any device for details & attributes'],
        ].map(([title, desc]) => (
          <div key={title} style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 8, padding: '10px 12px' }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: J.text, marginBottom: 3 }}>{title}</div>
            <div style={{ fontSize: 11, color: J.textMuted }}>{desc}</div>
          </div>
        ))}
      </div>
    </>
  );
}

function PermissionsSection() {
  return (
    <>
      <H2>Permissions & Access Control</H2>
      <P>JARVIS uses a role-based access control (RBAC) system. Users are assigned to groups, and groups have permission sets that determine what actions are allowed.</P>

      <H3>Permission Tiers</H3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
        {[
          { perm: 'any' as Perm, title: 'Any logged-in user', desc: 'All read-only skills — system monitoring, weather, news, calculations, Wikipedia, timers, memory, etc. No write access to the server.' },
          { perm: 'write' as Perm, title: 'Write group', desc: 'Everything in "Any user" plus: restart/start/stop services, control Docker containers, start/stop Proxmox VMs and LXC containers.' },
          { perm: 'admin' as Perm, title: 'Admin', desc: 'Full access including system shutdown/reboot, user management, audit log access, emergency stop override, and all admin dashboard features.' },
        ].map(({ perm, title, desc }) => {
          const badge = permBadgeStyle(perm);
          return (
          <div key={perm} style={{ background: J.bg2, border: `1px solid ${badge.color}33`, borderLeft: `3px solid ${badge.color}`, borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
              <PermBadge perm={perm} />
              <span style={{ fontSize: 13, fontWeight: 600, color: J.text }}>{title}</span>
            </div>
            <div style={{ fontSize: 12, color: J.textSec, lineHeight: 1.6 }}>{desc}</div>
          </div>
          );
        })}
      </div>

      <H3>Managing Groups</H3>
      <P>Groups and users are managed from the <strong>Admin Dashboard</strong> (<Tag>/dashboard</Tag>). An admin can:</P>
      <div style={{ paddingLeft: 16, borderLeft: `2px solid ${J.border}` }}>
        <P>• Create and delete groups</P>
        <P>• Add and remove users from groups</P>
        <P>• Assign permission sets to groups</P>
        <P>• View the full audit log of all actions</P>
        <P>• Enable or disable admin accounts</P>
      </div>

      <Note>The emergency stop feature immediately halts all write operations across all sessions. It can be toggled from the Admin Dashboard and is effective instantly.</Note>

      <H3>Adding a User to the Write Group</H3>
      <P>1. Go to <Tag>/dashboard</Tag> → Groups</P>
      <P>2. Click the group that has write permission (e.g. <Tag>operators</Tag>)</P>
      <P>3. Click <strong>Add Member</strong> and search for the user</P>
      <P>4. The user will have write access on their next message — no re-login required</P>
    </>
  );
}

function VoiceSetupSection() {
  return (
    <>
      <H2>Voice Setup</H2>
      <P>JARVIS supports two speech-to-text engines and two text-to-speech providers. Configure them via environment variables or the Settings screen.</P>

      <H3>Text-to-Speech (TTS)</H3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
        {[
          { name: 'Local (Kokoro / Coqui)', var: 'JARVIS_TTS_PROVIDER=local', desc: 'Runs entirely on your server — zero latency on LAN, no cloud calls. Requires a compatible TTS server running locally. Best for privacy.' },
          { name: 'Google Gemini TTS', var: 'JARVIS_TTS_PROVIDER=gemini', desc: 'Uses the Gemini API for high-quality neural voices. Requires JARVIS_GEMINI_API_KEY. Audio leaves your network.' },
        ].map(p => (
          <div key={p.name} style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: J.text, marginBottom: 4 }}>{p.name}</div>
            <code style={{ fontSize: 11, color: J.amber, fontFamily: 'JetBrains Mono,monospace', display: 'block', marginBottom: 6 }}>{p.var}</code>
            <div style={{ fontSize: 12, color: J.textSec }}>{p.desc}</div>
          </div>
        ))}
      </div>

      <H3>Speech-to-Text (STT)</H3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
        {[
          { name: 'Local (Whisper)', var: 'JARVIS_STT_PROVIDER=local', desc: 'Runs OpenAI Whisper on your hardware. Requires a Whisper server endpoint. No data leaves your network.' },
          { name: 'Google Gemini STT', var: 'JARVIS_STT_PROVIDER=gemini', desc: 'Uses the Gemini API for transcription. Fast and accurate. Requires JARVIS_GEMINI_API_KEY.' },
        ].map(p => (
          <div key={p.name} style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: J.text, marginBottom: 4 }}>{p.name}</div>
            <code style={{ fontSize: 11, color: J.amber, fontFamily: 'JetBrains Mono,monospace', display: 'block', marginBottom: 6 }}>{p.var}</code>
            <div style={{ fontSize: 12, color: J.textSec }}>{p.desc}</div>
          </div>
        ))}
      </div>

      <H3>Wake Word</H3>
      <P>Enable always-on voice detection so you can say a phrase to activate JARVIS without tapping the mic button.</P>
      <CodeBox>{`JARVIS_WAKEWORD_ENABLED=true
JARVIS_WAKEWORD_PHRASE="hey jarvis"`}</CodeBox>
      <P>The wake word phrase can also be changed at runtime via <strong>Admin Dashboard → Settings → Voice</strong>.</P>

      <H3>Voice Selection</H3>
      <P>Open <strong>Settings → Voice</strong> in the JARVIS interface. The available voices depend on your TTS provider. Local providers expose the voices installed on your TTS server; Gemini exposes its own set of neural voices.</P>

      <Note>Voice features require microphone permissions in the browser. HTTPS is required for mic access in Chrome and Edge — either serve JARVIS over HTTPS or use a local certificate.</Note>
    </>
  );
}

function TroubleshootingSection() {
  const issues = [
    {
      q: 'Login fails with "invalid credentials"',
      a: 'Double-check username and password. If you just set up JARVIS, the default admin account is created on first start — check the server logs for the generated password. Use Admin Dashboard → Users to reset it.',
    },
    {
      q: 'Voice / mic button does nothing',
      a: 'The browser needs microphone permission and HTTPS (or localhost). Check Settings → Voice to verify the STT provider is configured. Open the browser console for detailed errors.',
    },
    {
      q: 'Home Assistant shows "offline" or devices don\'t load',
      a: 'Verify JARVIS_HA_BASE_URL is reachable from the JARVIS server (not just your browser). Test with: curl $JARVIS_HA_BASE_URL/api/ -H "Authorization: Bearer $JARVIS_HA_TOKEN". Check HA long-lived token hasn\'t expired.',
    },
    {
      q: 'Proxmox screen shows no hosts or timeout',
      a: 'Ensure JARVIS_PROXMOX_HOST is reachable from the server and the API token has the right permissions. If SSL verification fails, set JARVIS_PROXMOX_VERIFY_SSL=false. Check the Proxmox firewall — the API port is 8006.',
    },
    {
      q: 'Skills answer with "I don\'t know" instead of running',
      a: 'Skills are matched by exact phrase patterns. Try the exact syntax shown in Docs → Skills Reference. Open the audit log to see what was dispatched. The LLM fallback is used when no skill matches.',
    },
    {
      q: 'Greeting overlay is stuck',
      a: 'Click anywhere or press Escape to dismiss. If TTS is playing and you can\'t stop it, the overlay auto-dismisses 4 seconds after typing finishes.',
    },
    {
      q: 'Admin dashboard returns 403',
      a: 'Admin routes require the admin token which is separate from the user session. The dashboard issues it automatically on load. Try logging out and back in. Confirm your user has role "admin" in the Users page.',
    },
  ];
  return (
    <>
      <H2>Troubleshooting</H2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {issues.map(({ q, a }) => (
          <div key={q} style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: J.text, marginBottom: 6 }}>{q}</div>
            <div style={{ fontSize: 12, color: J.textSec, lineHeight: 1.65 }}>{a}</div>
          </div>
        ))}
      </div>
    </>
  );
}

function Steps({ items }: { items: string[] }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
      {items.map((text, i) => (
        <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <div style={{ width: 24, height: 24, borderRadius: '50%', background: J.amberDim, border: `1px solid ${J.borderAccent}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: J.amber, flexShrink: 0 }}>{i + 1}</div>
          <div style={{ fontSize: 13, color: J.textSec, lineHeight: 1.6, paddingTop: 3 }}>{text}</div>
        </div>
      ))}
    </div>
  );
}

function DesktopAppSection() {
  return (
    <>
      <H2>Desktop App (PWA)</H2>
      <P>JARVIS ships a <Tag>manifest.json</Tag> with <Tag>display: standalone</Tag> — it installs as a native-feeling desktop or mobile app directly from the browser. No app store, no Electron, no installer.</P>
      <P>PWA installation requires HTTPS. The recommended approach for home lab use is <strong>Tailscale</strong>, which gives you a real HTTPS certificate and remote access from any device in one step.</P>

      <H3>Recommended: Tailscale (easiest for home lab)</H3>
      <P>Tailscale creates a private encrypted network (Tailnet) between all your devices and issues a real HTTPS certificate for your JARVIS server automatically — no port forwarding, no dynamic DNS, no self-signed cert warnings.</P>
      <Steps items={[
        'Install Tailscale on your JARVIS server: curl -fsSL https://tailscale.com/install.sh | sh',
        'Authenticate: sudo tailscale up',
        'Note your Tailscale hostname — it looks like my-server.tail12345.ts.net (shown in tailscale status)',
        'Enable HTTPS in the Tailscale admin console: go to DNS → Enable HTTPS Certificates',
        'Issue a certificate on the server: sudo tailscale cert my-server.tail12345.ts.net',
        'Configure nginx to use the certificate (see below), then open https://my-server.tail12345.ts.net in Chrome on any Tailnet device',
        'Install as PWA: click the install icon in the address bar or browser menu → Install JARVIS',
      ]} />
      <CodeBox>{`# Tailscale issues two files — use them directly in nginx
sudo tailscale cert my-server.tail12345.ts.net
# Creates: my-server.tail12345.ts.net.crt
#          my-server.tail12345.ts.net.key

server {
    listen 443 ssl;
    server_name my-server.tail12345.ts.net;

    ssl_certificate     /etc/ssl/certs/my-server.tail12345.ts.net.crt;
    ssl_certificate_key /etc/ssl/private/my-server.tail12345.ts.net.key;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_read_timeout 300s;
    }
}`}</CodeBox>
      <Note>With Tailscale you also get remote access from your phone anywhere in the world — install Tailscale on your phone and JARVIS is always reachable at the same <Tag>ts.net</Tag> URL.</Note>

      <H3>Alternative: mkcert (LAN only, no remote access)</H3>
      <P>If you prefer to stay fully local without Tailscale, <Tag>mkcert</Tag> creates a locally-trusted certificate for your LAN hostname.</P>
      <CodeBox>{`# Install and initialize mkcert
sudo apt install mkcert        # Debian/Ubuntu
mkcert -install                # installs local CA into browser trust store

# Generate cert for your server IP or hostname
mkcert jarvis.local 192.168.1.100
# Output: jarvis.local+1.pem  jarvis.local+1-key.pem

# Use in nginx the same way as above`}</CodeBox>

      <H3>Install on Desktop (Chrome / Edge)</H3>
      <Steps items={[
        'Open JARVIS at your HTTPS URL',
        'Click the install icon in the address bar (⊕ or monitor icon) — or open the browser menu (⋮) → "Install JARVIS" / "Install as app"',
        'Click Install — JARVIS opens in its own window without browser chrome',
        'A shortcut is added to your taskbar / Start Menu / Applications folder automatically',
      ]} />

      <H3>Install on Android</H3>
      <Steps items={[
        'Open JARVIS in Chrome on Android (over Tailscale or LAN)',
        'Tap the three-dot menu → "Add to Home screen"',
        'Confirm the name and tap Add',
        'JARVIS appears as a standalone app icon on your home screen',
      ]} />

      <H3>Install on iOS (Safari)</H3>
      <Steps items={[
        'Open JARVIS in Safari (Tailscale app must be running on iOS)',
        'Tap the Share button (square with arrow)',
        'Scroll down and tap "Add to Home Screen"',
        'Confirm and tap Add — JARVIS launches fullscreen with no browser chrome',
      ]} />
    </>
  );
}

function DeploymentSection() {
  return (
    <>
      <H2>Deployment & Operations</H2>

      <H3>Directory Structure</H3>
      <CodeBox>{`/opt/jarvis/
├── jarvis/               # Python backend (FastAPI)
│   ├── assistant_domain.py
│   ├── api_auth_chat.py
│   ├── api_admin.py
│   └── ...
├── frontend/dist/        # Built React SPA (served as static files)
├── data/                 # Runtime data (user store, audit log, etc.)
├── .env                  # All JARVIS_* env vars — never commit this
└── jarvis.service        # systemd unit file (copy to /etc/systemd/system/)`}</CodeBox>

      <H3>Environment Variables Reference</H3>
      <div style={{ border: `1px solid ${J.border}`, borderRadius: 10, overflow: 'hidden', marginBottom: 20 }}>
        {[
          ['JARVIS_SECRET_KEY', 'Secret key for JWT session tokens. Generate with: openssl rand -hex 32'],
          ['JARVIS_ADMIN_PASSWORD', 'Initial admin password (used only on first start if no users exist)'],
          ['JARVIS_LLM_PROVIDER', 'LLM backend: gemini · openai · local · anthropic'],
          ['JARVIS_GEMINI_API_KEY', 'Google Gemini API key (used for LLM, TTS and STT if provider=gemini)'],
          ['JARVIS_TTS_PROVIDER', 'TTS engine: local · gemini'],
          ['JARVIS_STT_PROVIDER', 'STT engine: local · gemini'],
          ['JARVIS_WAKEWORD_ENABLED', 'Enable wake word: true · false'],
          ['JARVIS_WAKEWORD_PHRASE', 'Wake word phrase, e.g. "hey jarvis"'],
          ['JARVIS_HA_BASE_URL', 'Home Assistant base URL, e.g. http://homeassistant.local:8123'],
          ['JARVIS_HA_TOKEN', 'Home Assistant long-lived access token'],
          ['JARVIS_PROXMOX_HOST', 'Proxmox hostname/IP (supports _0, _1 suffix for multiple hosts)'],
          ['JARVIS_PROXMOX_USER', 'Proxmox API user, e.g. root@pam'],
          ['JARVIS_PROXMOX_TOKEN_ID', 'Proxmox API token name'],
          ['JARVIS_PROXMOX_TOKEN_SECRET', 'Proxmox API token secret'],
          ['JARVIS_PROXMOX_VERIFY_SSL', 'Verify Proxmox SSL cert: true · false'],
          ['JARVIS_GITHUB_TOKEN', 'GitHub personal access token for RAG indexing'],
          ['JARVIS_WIKIJS_URL', 'WikiJS instance URL for RAG indexing'],
        ].map(([key, desc], i) => (
          <div key={key} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.5fr)', padding: '9px 14px', borderBottom: i < 16 ? `1px solid ${J.border}` : 'none', background: i % 2 === 1 ? J.bg2 : 'transparent', gap: 16, alignItems: 'center' }}>
            <code style={{ fontSize: 11, color: J.amber, fontFamily: 'JetBrains Mono,monospace', wordBreak: 'break-all' }}>{key}</code>
            <span style={{ fontSize: 12, color: J.textSec }}>{desc}</span>
          </div>
        ))}
      </div>

      <H3>systemd Service</H3>
      <P>The JARVIS systemd unit file at <Tag>/opt/jarvis/systemd/jarvis.service</Tag>. Copy it to enable auto-start:</P>
      <CodeBox>{`sudo cp /opt/jarvis/systemd/jarvis.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable jarvis
sudo systemctl start jarvis`}</CodeBox>
      <P>Common service management commands:</P>
      <CodeBox>{`sudo systemctl status jarvis      # check if running
sudo systemctl restart jarvis     # restart after config changes
sudo journalctl -u jarvis -f      # follow live logs
sudo journalctl -u jarvis -n 100  # last 100 log lines`}</CodeBox>

      <H3>Deploying Frontend Changes</H3>
      <P>After running <Tag>npm run build</Tag> in <Tag>frontend/</Tag>, copy the output to production:</P>
      <CodeBox>{`sudo cp frontend/dist/assets/index.js  /opt/jarvis/frontend/dist/assets/index.js
sudo cp frontend/dist/assets/index.css /opt/jarvis/frontend/dist/assets/index.css
sudo cp frontend/dist/index.html        /opt/jarvis/frontend/dist/index.html
sudo systemctl restart jarvis`}</CodeBox>

      <H3>Backup</H3>
      <P>JARVIS stores all runtime data in <Tag>/opt/jarvis/data/</Tag>. A full backup is just a directory copy:</P>
      <CodeBox>{`# Backup
sudo tar czf jarvis-backup-$(date +%Y%m%d).tar.gz /opt/jarvis/data/ /opt/jarvis/.env

# Restore
sudo tar xzf jarvis-backup-YYYYMMDD.tar.gz -C /
sudo systemctl restart jarvis`}</CodeBox>
    </>
  );
}

// ── Top-level component ───────────────────────────────────────────────────────

type SectionId = 'overview' | 'getting-started' | 'skills' | 'proxmox' | 'homeassistant' | 'permissions' | 'voice' | 'troubleshooting' | 'desktop-app' | 'deployment';

interface SideEntry {
  id: SectionId;
  label: string;
  icon: (p: { size?: number }) => JSX.Element;
  adminOnly?: boolean;
  group?: string;
}

const SIDES: SideEntry[] = [
  { id: 'overview',        label: 'Overview',          icon: IconActivity,  group: 'General' },
  { id: 'getting-started', label: 'Getting Started',   icon: IconKey,       group: 'General' },
  { id: 'skills',          label: 'Skills Reference',  icon: IconCode,      group: 'General' },
  { id: 'voice',           label: 'Voice Setup',       icon: IconMic,       group: 'General' },
  { id: 'troubleshooting', label: 'Troubleshooting',   icon: IconActivity,  group: 'General' },
  { id: 'proxmox',         label: 'Proxmox Setup',     icon: IconServer,    group: 'Integrations' },
  { id: 'homeassistant',   label: 'Home Assistant',    icon: IconSettings,  group: 'Integrations' },
  { id: 'permissions',     label: 'Permissions',       icon: IconShield,    group: 'Integrations' },
  { id: 'desktop-app',     label: 'Desktop App',       icon: IconMemory,    group: 'Admin', adminOnly: true },
  { id: 'deployment',      label: 'Deployment & Ops',  icon: IconServer,    group: 'Admin', adminOnly: true },
];

function resolveRagState(data: RagStatus | null, error: boolean): IntegrationState {
  if (!data && !error) return 'loading';
  if (error) return 'unknown';
  const totalDocs = Object.values(data!.counts).reduce((sum, n) => sum + n, 0);
  return data!.updated_at > 0 && totalDocs > 0 ? 'active' : 'inactive';
}

function resolveHaState(data: HomeAssistantHealth | null, error: boolean): IntegrationState {
  if (!data && !error) return 'loading';
  if (error) return 'unknown';
  return data!.integration?.configured && data!.integration?.healthy ? 'active' : 'inactive';
}

export function DocsScreen() {
  useJ();
  const [section, setSection] = useState<SectionId>('overview');
  const [search, setSearch] = useState('');
  const [ragData, setRagData] = useState<RagStatus | null>(null);
  const [ragError, setRagError] = useState(false);
  const [haData, setHaData] = useState<HomeAssistantHealth | null>(null);
  const [haError, setHaError] = useState(false);

  useEffect(() => {
    getRagStatus()
      .then(d => setRagData(d))
      .catch(() => setRagError(true));
    fetchHomeAssistantHealth()
      .then(d => setHaData(d))
      .catch(() => setHaError(true));
  }, []);

  const integrations: IntegrationStatuses = {
    rag: resolveRagState(ragData, ragError),
    homeAssistant: resolveHaState(haData, haError),
  };

  const user = getStoredUser();
  const isAdmin = user?.role === 'admin';

  const visibleSides = SIDES.filter(s => !s.adminOnly || isAdmin);
  const groups = [...new Set(visibleSides.map(s => s.group))];

  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden', background: J.bg1 }}>
      {/* Sidebar */}
      <div style={{ width: 210, flexShrink: 0, borderRight: `1px solid ${J.border}`, padding: '16px 8px', overflowY: 'auto', background: J.bg1 }}>
        {groups.map(group => (
          <div key={group} style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 10, color: J.textMuted, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600, padding: '2px 10px 8px', display: 'flex', alignItems: 'center', gap: 5 }}>
              {group}
              {group === 'Admin' && <span style={{ fontSize: 9, background: J.amberDim, color: J.amber, border: `1px solid ${J.borderAccent}`, borderRadius: 3, padding: '1px 5px', fontWeight: 700 }}>ADMIN</span>}
            </div>
            {visibleSides.filter(s => s.group === group).map(s => (
              <button key={s.id} onClick={() => setSection(s.id)}
                style={{ width: '100%', textAlign: 'left', background: section === s.id ? J.bg2 : 'none', border: section === s.id ? `1px solid ${J.border}` : '1px solid transparent', color: section === s.id ? J.text : J.textSec, borderRadius: 8, padding: '7px 11px', fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2, transition: 'all .1s' }}
                onMouseEnter={e => { if (section !== s.id) e.currentTarget.style.background = J.bg2; }}
                onMouseLeave={e => { if (section !== s.id) e.currentTarget.style.background = 'none'; }}>
                <span style={{ color: section === s.id ? J.amber : J.textMuted }}><s.icon size={13} /></span>
                {s.label}
              </button>
            ))}
          </div>
        ))}
        <div style={{ borderTop: `1px solid ${J.border}`, margin: '8px 6px 0', paddingTop: 12 }}>
          <div style={{ fontSize: 11, color: J.textMuted, padding: '0 5px', lineHeight: 1.5 }}>
            JARVIS V1<br />
            {isAdmin && <a href="/dashboard" style={{ color: J.amber, textDecoration: 'none' }}>Admin Dashboard →</a>}
          </div>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '32px 40px', maxWidth: 860 }}>
        {section === 'skills' && (
          <div style={{ marginBottom: 18 }}>
            <div style={{ position: 'relative' }}>
              <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: J.textMuted, pointerEvents: 'none' }}><IconSearch size={13} /></span>
              <input className="j-input" placeholder="Search skills…" value={search} onChange={e => setSearch(e.target.value)}
                style={{ width: '100%', padding: '9px 12px 9px 34px', borderRadius: 9, fontSize: 13 }} />
            </div>
          </div>
        )}
        {section === 'overview'        && <OverviewSection />}
        {section === 'getting-started' && <GettingStartedSection />}
        {section === 'skills'          && <SkillsSection search={search} integrations={integrations} />}
        {section === 'voice'           && <VoiceSetupSection />}
        {section === 'troubleshooting' && <TroubleshootingSection />}
        {section === 'proxmox'         && <ProxmoxSection />}
        {section === 'homeassistant'   && <HomeAssistantSection status={integrations.homeAssistant} />}
        {section === 'permissions'     && <PermissionsSection />}
        {section === 'desktop-app'     && (isAdmin ? <DesktopAppSection /> : null)}
        {section === 'deployment'      && (isAdmin ? <DeploymentSection /> : null)}
      </div>
    </div>
  );
}
