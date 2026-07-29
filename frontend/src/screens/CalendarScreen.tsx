import { useEffect, useState } from 'react';
import { J, useJ, Spinner, showToast, IconPlus, IconTrash, IconX, IconCalendar, IconRefresh, IconSettings } from './jarvis-shared';
import { OverlayDialog } from '../shared/ui/OverlayDialog';
import {
  CalendarEvent, createCalendarEvent, deleteCalendarCredentials, deleteCalendarEvent, fetchCalendarCredentialsStatus,
  fetchCalendarEvents, setCalendarCredentials, syncCalendar,
} from '../shared/api/calendar';

function toLocalInputValue(epoch: number): string {
  const d = new Date(epoch * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fromLocalInputValue(value: string): number {
  return Math.floor(new Date(value).getTime() / 1000);
}

function defaultStartValue(): string {
  const d = new Date(Date.now() + 60 * 60 * 1000);
  d.setMinutes(0, 0, 0);
  return toLocalInputValue(Math.floor(d.getTime() / 1000));
}

function ConnectCalendarPanel({ onConnected }: { onConnected: () => void }) {
  const [url, setUrl] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!url.trim() || !username.trim() || !password.trim() || saving) return;
    setSaving(true);
    try {
      await setCalendarCredentials({ url: url.trim(), username: username.trim(), password });
      showToast('Calendar connected', 'success');
      onConnected();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to connect calendar', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ maxWidth: 420, margin: '48px auto', background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 14, padding: 28 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <IconCalendar size={20} />
        <div style={{ fontSize: 16, fontWeight: 600, color: J.text }}>Connect your calendar</div>
      </div>
      <div style={{ fontSize: 12.5, color: J.textSec, marginBottom: 12, lineHeight: 1.6 }}>
        Enter your CalDAV account details (Google Calendar, iCloud, Nextcloud, or any CalDAV server).
      </div>
      <div style={{ fontSize: 11.5, color: J.textMuted, marginBottom: 20, lineHeight: 1.6 }}>
        For iCloud: use <code>https://caldav.icloud.com</code> as the URL and your Apple ID as the username.
        Generate an app-specific password at appleid.apple.com → Sign-In and Security → App-Specific Passwords —
        your regular Apple ID password will not work.
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>CalDAV URL</label>
          <input className="j-input" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://caldav.example.com/calendars/me/home/"
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
        </div>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>Username</label>
          <input className="j-input" value={username} onChange={e => setUsername(e.target.value)}
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
        </div>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>Password / App Password</label>
          <input className="j-input" type="password" value={password} onChange={e => setPassword(e.target.value)}
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
        </div>
        <button onClick={submit} disabled={!url.trim() || !username.trim() || !password.trim() || saving} className="j-btn"
          style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '10px 16px', fontSize: 13, fontWeight: 600, justifyContent: 'center', opacity: saving ? .7 : 1, marginTop: 4 }}>
          {saving ? <Spinner size={13} color={J.bg0} /> : 'Connect'}
        </button>
      </div>
    </div>
  );
}

function ManageCalendarDialog({ onClose, onUpdated, onDisconnected }: { onClose: () => void; onUpdated: () => void; onDisconnected: () => void }) {
  const [url, setUrl] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  const submit = async () => {
    if (!url.trim() || !username.trim() || !password.trim() || saving) return;
    setSaving(true);
    try {
      await setCalendarCredentials({ url: url.trim(), username: username.trim(), password });
      showToast('Calendar connection updated', 'success');
      onUpdated();
      onClose();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to update calendar', 'error');
    } finally {
      setSaving(false);
    }
  };

  const disconnect = async () => {
    setDisconnecting(true);
    try {
      await deleteCalendarCredentials();
      showToast('Calendar disconnected', 'info');
      onDisconnected();
      onClose();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to disconnect calendar', 'error');
    } finally {
      setDisconnecting(false);
    }
  };

  return (
    <OverlayDialog
      title="Manage Calendar Connection"
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>Cancel</button>
          <button onClick={submit} disabled={!url.trim() || !username.trim() || !password.trim() || saving} className="j-btn"
            style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600, opacity: url.trim() && username.trim() && password.trim() ? 1 : .5 }}>
            {saving ? <Spinner size={13} color={J.bg0} /> : 'Save'}
          </button>
        </>
      }
    >
      <div style={{ fontSize: 12.5, color: J.textSec, marginBottom: 10, lineHeight: 1.6 }}>
        Re-enter your CalDAV details to change the connected account, or disconnect below.
        For security, existing credentials are never shown here.
      </div>
      <div style={{ fontSize: 11.5, color: J.textMuted, marginBottom: 16, lineHeight: 1.6 }}>
        For iCloud: use <code>https://caldav.icloud.com</code> as the URL and your Apple ID as the username.
        Generate an app-specific password at appleid.apple.com → Sign-In and Security → App-Specific Passwords —
        your regular Apple ID password will not work.
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>CalDAV URL</label>
          <input className="j-input" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://caldav.example.com/calendars/me/home/"
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
        </div>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>Username</label>
          <input className="j-input" value={username} onChange={e => setUsername(e.target.value)}
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
        </div>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>Password / App Password</label>
          <input className="j-input" type="password" value={password} onChange={e => setPassword(e.target.value)}
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
        </div>
      </div>
      <div style={{ marginTop: 20, paddingTop: 16, borderTop: `1px solid ${J.border}` }}>
        {!confirmDisconnect ? (
          <button onClick={() => setConfirmDisconnect(true)} className="j-btn"
            style={{ background: 'none', border: `1px solid ${J.error}30`, color: J.error, borderRadius: 8, padding: '8px 14px', fontSize: 12.5 }}>
            <IconTrash size={12} /> Disconnect calendar
          </button>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 12.5, color: J.textSec }}>Remove this calendar connection?</span>
            <button onClick={disconnect} disabled={disconnecting} className="j-btn"
              style={{ background: J.error, color: '#fff', borderRadius: 7, padding: '6px 14px', fontSize: 12.5, fontWeight: 600 }}>
              {disconnecting ? <Spinner size={12} color="#fff" /> : 'Yes, disconnect'}
            </button>
            <button onClick={() => setConfirmDisconnect(false)} className="j-btn"
              style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 7, padding: '6px 14px', fontSize: 12.5 }}>
              Cancel
            </button>
          </div>
        )}
      </div>
    </OverlayDialog>
  );
}

function CreateEventModal({ onClose, onCreated }: { onClose: () => void; onCreated: (event: CalendarEvent) => void }) {
  const [title, setTitle] = useState('');
  const [start, setStart] = useState(defaultStartValue());
  const [end, setEnd] = useState(() => {
    const d = new Date(fromLocalInputValue(defaultStartValue()) * 1000 + 60 * 60 * 1000);
    return toLocalInputValue(Math.floor(d.getTime() / 1000));
  });
  const [location, setLocation] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const [conflicts, setConflicts] = useState<CalendarEvent[] | null>(null);

  const submit = async (force = false) => {
    const trimmed = title.trim();
    const startEpoch = fromLocalInputValue(start);
    const endEpoch = fromLocalInputValue(end);
    if (!trimmed || !start || !end || endEpoch <= startEpoch || saving) return;
    setSaving(true);
    try {
      const res = await createCalendarEvent({ title: trimmed, start: startEpoch, end: endEpoch, location: location.trim() || undefined, description: description.trim() || undefined, force });
      if (!res.created) {
        setConflicts(res.conflicts);
        showToast('That overlaps with an existing event', 'error');
        return;
      }
      onCreated(res.event as CalendarEvent);
      showToast('Event created', 'success');
      onClose();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to create event', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <OverlayDialog
      title="New Event"
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose} className="j-btn" style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '8px 16px', fontSize: 13 }}>Cancel</button>
          {conflicts ? (
            <button onClick={() => submit(true)} disabled={saving} className="j-btn"
              style={{ background: J.error, color: '#fff', borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600 }}>
              {saving ? <Spinner size={13} color="#fff" /> : 'Book anyway'}
            </button>
          ) : (
            <button onClick={() => submit(false)} disabled={!title.trim() || saving} className="j-btn"
              style={{ background: J.amber, color: J.bg0, borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600, opacity: title.trim() ? 1 : .5 }}>
              {saving ? <Spinner size={13} color={J.bg0} /> : 'Create'}
            </button>
          )}
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>Title</label>
          <input className="j-input" autoFocus value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Design review"
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>Start</label>
            <input className="j-input" type="datetime-local" value={start} onChange={e => { setStart(e.target.value); setConflicts(null); }}
              style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>End</label>
            <input className="j-input" type="datetime-local" value={end} onChange={e => { setEnd(e.target.value); setConflicts(null); }}
              style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
          </div>
        </div>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>Location (optional)</label>
          <input className="j-input" value={location} onChange={e => setLocation(e.target.value)}
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
        </div>
        <div>
          <label style={{ fontSize: 12, color: J.textSec, display: 'block', marginBottom: 5 }}>Description (optional)</label>
          <textarea className="j-input" value={description} onChange={e => setDescription(e.target.value)} rows={2}
            style={{ width: '100%', borderRadius: 8, padding: '9px 12px', fontSize: 13, resize: 'vertical', fontFamily: 'inherit' }} />
        </div>
        {conflicts && conflicts.length > 0 && (
          <div style={{ background: J.errorDim, border: `1px solid ${J.error}`, borderRadius: 8, padding: '10px 12px', fontSize: 12.5, color: J.error }}>
            Overlaps with: {conflicts.map(c => c.title).join(', ')}. Choose another time, or book anyway.
          </div>
        )}
      </div>
    </OverlayDialog>
  );
}

function EventCard({ event, onDelete }: { event: CalendarEvent; onDelete: (id: string) => void }) {
  const start = new Date(event.start * 1000);
  const end = new Date(event.end * 1000);
  return (
    <div style={{ background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 12, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: J.text }}>{event.title}</div>
        <button onClick={() => onDelete(event.id)} title="Delete event" aria-label="Delete event"
          style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textMuted, borderRadius: 6, width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
          <IconTrash size={13} />
        </button>
      </div>
      <div style={{ fontSize: 12, color: J.textSec }}>
        {start.toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
        {' – '}
        {end.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
      </div>
      {event.location && <div style={{ fontSize: 12, color: J.textMuted }}>{event.location}</div>}
      {event.description && <div style={{ fontSize: 12, color: J.textSec, lineHeight: 1.5 }}>{event.description}</div>}
    </div>
  );
}

export function CalendarScreen(_props: { onNavigate?: (screen: string) => void }) {
  useJ();
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showManage, setShowManage] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchCalendarCredentialsStatus()
      .then(res => {
        setConfigured(res.status.configured);
        if (!res.status.configured) { setLoading(false); return; }
        const now = Math.floor(Date.now() / 1000) - 86400;
        return fetchCalendarEvents(now).then(r => setEvents(r.events));
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load calendar'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await syncCalendar();
      const now = Math.floor(Date.now() / 1000) - 86400;
      const res = await fetchCalendarEvents(now);
      setEvents(res.events);
      showToast('Calendar synced', 'success');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Sync failed', 'error');
    } finally {
      setSyncing(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteCalendarEvent(id);
      setEvents(prev => prev.filter(e => e.id !== id));
      showToast('Event deleted', 'info');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to delete event', 'error');
    }
  };

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: J.bg0 }}>
      <div style={{ height: 50, borderBottom: `1px solid ${J.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px', background: J.bg1, flexShrink: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: J.text }}>Calendar</div>
        {configured && (
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={handleSync} disabled={syncing} className="j-btn"
              style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, padding: '6px 12px', fontSize: 13 }}>
              {syncing ? <Spinner size={13} /> : <IconRefresh size={13} />} Sync
            </button>
            <button onClick={() => setShowCreate(true)} className="j-btn"
              style={{ background: J.amberDim, border: `1px solid ${J.borderAccent}`, color: J.amber, borderRadius: 8, padding: '6px 14px', fontSize: 13, fontWeight: 500 }}>
              <IconPlus size={13} /> New Event
            </button>
            <button onClick={() => setShowManage(true)} title="Manage connection" aria-label="Manage calendar connection" className="j-btn"
              style={{ background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, borderRadius: 8, width: 32, padding: 0, justifyContent: 'center' }}>
              <IconSettings size={13} />
            </button>
          </div>
        )}
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '22px 24px' }}>
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: J.textMuted, fontSize: 13, padding: '24px 0' }}>
            <Spinner size={14} /> Loading calendar...
          </div>
        )}

        {!loading && error && (
          <div style={{ background: J.errorDim, border: `1px solid ${J.error}`, borderRadius: 10, padding: '12px 16px', color: J.error, fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            {error}
            <button onClick={load} style={{ background: 'none', border: 'none', color: J.error, cursor: 'pointer', display: 'flex' }}><IconX size={14} /></button>
          </div>
        )}

        {!loading && !error && configured === false && (
          <ConnectCalendarPanel onConnected={load} />
        )}

        {!loading && !error && configured && events.length === 0 && (
          <div style={{ textAlign: 'center', color: J.textMuted, fontSize: 13, padding: '48px 0' }}>
            Nothing scheduled. Create an event or sync to pull in your calendar.
          </div>
        )}

        {!loading && !error && configured && events.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))', gap: 10 }}>
            {events.map(ev => <EventCard key={ev.id} event={ev} onDelete={handleDelete} />)}
          </div>
        )}
      </div>
      {showCreate && (
        <CreateEventModal onClose={() => setShowCreate(false)} onCreated={ev => setEvents(prev => [...prev, ev].sort((a, b) => a.start - b.start))} />
      )}
      {showManage && (
        <ManageCalendarDialog
          onClose={() => setShowManage(false)}
          onUpdated={load}
          onDisconnected={() => { setConfigured(false); setEvents([]); }}
        />
      )}
    </div>
  );
}
