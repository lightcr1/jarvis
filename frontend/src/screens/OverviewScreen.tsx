import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { J, useJ, Spinner, IconFile, IconFolder, IconMail, IconCalendar, IconMonitor } from './jarvis-shared';
import { getStoredUser } from '../shared/api/client';
import { browseFiles, formatBytes, type FileEntry, type FileFolder } from '../shared/api/files';
import { fetchCalendarCredentialsStatus, fetchCalendarEvents, type CalendarEvent } from '../shared/api/calendar';
import { fetchEmailCredentialsStatus, fetchEmailMessages } from '../shared/api/email';
import { fetchWorkspaceTargets, type WorkspaceTarget } from '../shared/api/workspace';

type RecentDriveItem = { kind: 'folder' | 'file'; id: string; name: string; updated_at: number; size_bytes?: number };

function greetingForHour(hour: number): string {
  if (hour < 5) return 'Still up';
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: J.bg1, border: `1px solid ${J.border}`, borderRadius: 12, padding: 16, display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
      <h4 style={{ margin: '0 0 8px', fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em', color: J.textMuted, fontWeight: 600 }}>{title}</h4>
      {children}
    </div>
  );
}

function CardRow({ icon, children, meta }: { icon: React.ReactNode; children: React.ReactNode; meta?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', fontSize: 13, borderTop: `1px solid ${J.border}`, color: J.text }}>
      <div style={{ width: 26, height: 26, borderRadius: 6, background: J.amberDim, color: J.amber, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        {icon}
      </div>
      <div style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{children}</div>
      {meta && <span style={{ color: J.textMuted, fontSize: 11, fontFamily: 'ui-monospace, monospace', flexShrink: 0 }}>{meta}</span>}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div style={{ fontSize: 12.5, color: J.textMuted, padding: '10px 0 2px' }}>{children}</div>;
}

function timeAgo(ts: number): string {
  const diffSec = Math.max(0, Math.floor(Date.now() / 1000) - ts);
  if (diffSec < 60) return 'just now';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

export function OverviewScreen() {
  useJ();
  const navigate = useNavigate();
  const user = getStoredUser();

  const [loadingDrive, setLoadingDrive] = useState(true);
  const [recentDrive, setRecentDrive] = useState<RecentDriveItem[]>([]);

  const [loadingCalendar, setLoadingCalendar] = useState(true);
  const [calendarConfigured, setCalendarConfigured] = useState(false);
  const [upcomingEvents, setUpcomingEvents] = useState<CalendarEvent[]>([]);

  const [loadingEmail, setLoadingEmail] = useState(true);
  const [emailConfigured, setEmailConfigured] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  const [loadingDesktop, setLoadingDesktop] = useState(true);
  const [targets, setTargets] = useState<WorkspaceTarget[]>([]);

  useEffect(() => {
    browseFiles(null)
      .then(res => {
        const folderItems: RecentDriveItem[] = res.folders.map((f: FileFolder) => ({ kind: 'folder', id: f.id, name: f.name, updated_at: f.updated_at }));
        const fileItems: RecentDriveItem[] = res.files.map((f: FileEntry) => ({ kind: 'file', id: f.id, name: f.filename, updated_at: f.updated_at, size_bytes: f.size_bytes }));
        const merged = [...folderItems, ...fileItems].sort((a, b) => b.updated_at - a.updated_at).slice(0, 4);
        setRecentDrive(merged);
      })
      .catch(() => {})
      .finally(() => setLoadingDrive(false));

    fetchCalendarCredentialsStatus()
      .then(res => {
        setCalendarConfigured(res.status.configured);
        if (!res.status.configured) return undefined;
        const now = Math.floor(Date.now() / 1000);
        return fetchCalendarEvents(now).then(r => setUpcomingEvents(r.events.slice(0, 3)));
      })
      .catch(() => {})
      .finally(() => setLoadingCalendar(false));

    fetchEmailCredentialsStatus()
      .then(res => {
        setEmailConfigured(res.status.configured);
        if (!res.status.configured) return undefined;
        return fetchEmailMessages({ unreadOnly: true }).then(r => setUnreadCount(r.messages.length));
      })
      .catch(() => {})
      .finally(() => setLoadingEmail(false));

    fetchWorkspaceTargets()
      .then(res => setTargets(res.targets.slice(0, 4)))
      .catch(() => {})
      .finally(() => setLoadingDesktop(false));
  }, []);

  const hour = new Date().getHours();
  const displayName = user?.username || 'there';

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: J.bg0 }}>
      <div style={{ maxWidth: 980, margin: '0 auto', padding: '28px 24px 40px' }}>
        <div style={{ fontSize: 21, fontWeight: 700, color: J.text, marginBottom: 3 }}>{greetingForHour(hour)}, {displayName}.</div>
        <div style={{ fontSize: 12.5, color: J.textSec, marginBottom: 22 }}>
          {loadingDrive || loadingCalendar || loadingEmail || loadingDesktop
            ? 'Gathering the latest…'
            : `${recentDrive.length} recent item${recentDrive.length === 1 ? '' : 's'} in Drive · ${emailConfigured ? `${unreadCount} unread` : 'mail not connected'} · ${targets.length} workspace machine${targets.length === 1 ? '' : 's'}`}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14 }}>
          <Card title="Recent in Drive">
            {loadingDrive ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: J.textMuted, fontSize: 13 }}><Spinner size={13} /> Loading…</div>
            ) : recentDrive.length === 0 ? (
              <Empty>Nothing here yet. <a onClick={() => navigate('/workspace/files')} style={{ color: J.amber, cursor: 'pointer' }}>Open Drive</a> to add something.</Empty>
            ) : (
              recentDrive.map(item => (
                <CardRow key={item.id} icon={item.kind === 'folder' ? <IconFolder size={13} /> : <IconFile size={13} />} meta={timeAgo(item.updated_at)}>
                  {item.name}{item.size_bytes !== undefined ? ` · ${formatBytes(item.size_bytes)}` : ''}
                </CardRow>
              ))
            )}
          </Card>

          <Card title="Mail & Calendar">
            {loadingCalendar || loadingEmail ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: J.textMuted, fontSize: 13 }}><Spinner size={13} /> Loading…</div>
            ) : !emailConfigured && !calendarConfigured ? (
              <Empty>Not connected yet — set this up in <a onClick={() => navigate('/workspace/communication')} style={{ color: J.amber, cursor: 'pointer' }}>Mail &amp; Calendar</a>.</Empty>
            ) : (
              <>
                {emailConfigured && (
                  <CardRow icon={<IconMail size={13} />}>
                    {unreadCount === 0 ? 'No unread mail' : `${unreadCount} unread message${unreadCount === 1 ? '' : 's'}`}
                  </CardRow>
                )}
                {calendarConfigured && upcomingEvents.length === 0 && <CardRow icon={<IconCalendar size={13} />}>Nothing scheduled</CardRow>}
                {calendarConfigured && upcomingEvents.map(ev => (
                  <CardRow key={ev.id} icon={<IconCalendar size={13} />} meta={new Date(ev.start * 1000).toLocaleDateString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit' })}>
                    {ev.title}
                  </CardRow>
                ))}
              </>
            )}
          </Card>

          <Card title="Desktop">
            {loadingDesktop ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: J.textMuted, fontSize: 13 }}><Spinner size={13} /> Loading…</div>
            ) : targets.length === 0 ? (
              <Empty>No machines added yet. <a onClick={() => navigate('/workspace/desktop')} style={{ color: J.amber, cursor: 'pointer' }}>Add one</a>.</Empty>
            ) : (
              targets.map(t => <CardRow key={t.id} icon={<IconMonitor size={13} />}>{t.name}</CardRow>)
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
