import { J } from './jarvis-shared';
import type { CalendarEvent } from '../shared/api/calendar';

export type CalendarViewMode = 'month' | 'week' | 'workweek' | 'day';

const DOW_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const HOUR_ROW_PX = 44;
const EVENT_COLORS = [J.amber, J.blue, J.success];

function startOfDay(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

function addDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function mondayOf(d: Date): Date {
  const dow = (d.getDay() + 6) % 7; // Monday = 0
  return addDays(startOfDay(d), -dow);
}

export function rangeForView(anchor: Date, mode: CalendarViewMode): { start: Date; end: Date } {
  if (mode === 'day') {
    const s = startOfDay(anchor);
    return { start: s, end: addDays(s, 1) };
  }
  if (mode === 'week' || mode === 'workweek') {
    const monday = mondayOf(anchor);
    return { start: monday, end: addDays(monday, mode === 'workweek' ? 5 : 7) };
  }
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const gridStart = mondayOf(first);
  return { start: gridStart, end: addDays(gridStart, 42) };
}

export function stepAnchor(anchor: Date, mode: CalendarViewMode, dir: 1 | -1): Date {
  if (mode === 'day') return addDays(anchor, dir);
  if (mode === 'week' || mode === 'workweek') return addDays(anchor, dir * 7);
  const d = new Date(anchor);
  d.setMonth(d.getMonth() + dir);
  return d;
}

export function formatRangeLabel(anchor: Date, mode: CalendarViewMode): string {
  if (mode === 'month') return anchor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  if (mode === 'day') return anchor.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
  const { start, end } = rangeForView(anchor, mode);
  const last = addDays(end, -1);
  const sameMonth = start.getMonth() === last.getMonth();
  const startLabel = start.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  const endLabel = last.toLocaleDateString(undefined, sameMonth ? { day: 'numeric', year: 'numeric' } : { month: 'short', day: 'numeric', year: 'numeric' });
  return `${startLabel} – ${endLabel}`;
}

function colorFor(eventId: string): string {
  let hash = 0;
  for (let i = 0; i < eventId.length; i++) hash = (hash * 31 + eventId.charCodeAt(i)) % 997;
  return EVENT_COLORS[hash % EVENT_COLORS.length];
}

function MonthGrid({ anchor, events, onSelectDay, onEditEvent }: {
  anchor: Date; events: CalendarEvent[]; onSelectDay: (d: Date) => void; onEditEvent: (e: CalendarEvent) => void;
}) {
  const { start } = rangeForView(anchor, 'month');
  const today = new Date();
  const cells = Array.from({ length: 42 }, (_, i) => addDays(start, i));

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', background: J.bg0, border: `1px solid ${J.border}`, borderRadius: 10, overflow: 'hidden' }}>
      {DOW_LABELS.map(label => (
        <div key={label} style={{ fontFamily: 'ui-monospace, monospace', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: J.textMuted, textAlign: 'center', padding: '8px 0', borderBottom: `1px solid ${J.border}` }}>
          {label}
        </div>
      ))}
      {cells.map((day, i) => {
        const dayEvents = events.filter(ev => sameDay(new Date(ev.start * 1000), day));
        const isToday = sameDay(day, today);
        const isCurrentMonth = day.getMonth() === anchor.getMonth();
        return (
          <div key={i} onClick={() => onSelectDay(day)} style={{
            minHeight: 84, borderRight: (i + 1) % 7 === 0 ? 'none' : `1px solid ${J.border}`, borderBottom: `1px solid ${J.border}`,
            padding: '6px 7px', cursor: 'pointer', opacity: isCurrentMonth ? 1 : 0.4,
          }}>
            <div style={{
              fontSize: 12, fontFamily: 'ui-monospace, monospace', color: isToday ? J.bg0 : J.textMuted,
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              width: isToday ? 20 : undefined, height: isToday ? 20 : undefined,
              borderRadius: isToday ? '50%' : 0, background: isToday ? J.amber : 'transparent', fontWeight: isToday ? 700 : 400,
            }}>
              {day.getDate()}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 4 }}>
              {dayEvents.slice(0, 3).map(ev => (
                <div key={ev.id} onClick={e => { e.stopPropagation(); onEditEvent(ev); }} title={ev.title} style={{
                  fontSize: 10.5, padding: '2px 6px', borderRadius: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  background: `${colorFor(ev.id)}22`, color: colorFor(ev.id), borderLeft: `2px solid ${colorFor(ev.id)}`,
                }}>
                  {ev.title}
                </div>
              ))}
              {dayEvents.length > 3 && (
                <div style={{ fontSize: 10, color: J.textMuted, paddingLeft: 6 }}>+{dayEvents.length - 3} more</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TimeGrid({ anchor, mode, events, onEditEvent }: {
  anchor: Date; mode: 'week' | 'workweek' | 'day'; events: CalendarEvent[]; onEditEvent: (e: CalendarEvent) => void;
}) {
  const { start } = rangeForView(anchor, mode);
  const dayCount = mode === 'day' ? 1 : mode === 'workweek' ? 5 : 7;
  const days = Array.from({ length: dayCount }, (_, i) => addDays(start, i));
  const today = new Date();
  const hours = Array.from({ length: 24 }, (_, h) => h);

  return (
    <div style={{ border: `1px solid ${J.border}`, borderRadius: 10, overflow: 'hidden', background: J.bg0 }}>
      <div style={{ display: 'grid', gridTemplateColumns: `56px repeat(${dayCount}, 1fr)`, borderBottom: `1px solid ${J.border}` }}>
        <div />
        {days.map(day => {
          const isToday = sameDay(day, today);
          return (
            <div key={day.toISOString()} style={{ textAlign: 'center', padding: '8px 4px', borderLeft: `1px solid ${J.border}` }}>
              <div style={{ fontFamily: 'ui-monospace, monospace', fontSize: 10, letterSpacing: '0.06em', textTransform: 'uppercase', color: J.textMuted }}>
                {day.toLocaleDateString(undefined, { weekday: 'short' })}
              </div>
              <div style={{ fontSize: 13, fontWeight: isToday ? 700 : 500, color: isToday ? J.amber : J.text }}>{day.getDate()}</div>
            </div>
          );
        })}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: `56px repeat(${dayCount}, 1fr)`, maxHeight: 560, overflowY: 'auto' }}>
        <div>
          {hours.map(h => (
            <div key={h} style={{ height: HOUR_ROW_PX, fontSize: 10, color: J.textMuted, fontFamily: 'ui-monospace, monospace', textAlign: 'right', paddingRight: 8, borderTop: `1px solid ${J.border}`, boxSizing: 'border-box' }}>
              {h === 0 ? '' : `${String(h).padStart(2, '0')}:00`}
            </div>
          ))}
        </div>
        {days.map(day => {
          const dayEvents = events.filter(ev => sameDay(new Date(ev.start * 1000), day));
          return (
            <div key={day.toISOString()} style={{ position: 'relative', borderLeft: `1px solid ${J.border}` }}>
              {hours.map(h => (
                <div key={h} style={{ height: HOUR_ROW_PX, borderTop: `1px solid ${J.border}`, boxSizing: 'border-box' }} />
              ))}
              {dayEvents.map(ev => {
                const startD = new Date(ev.start * 1000);
                const endD = new Date(ev.end * 1000);
                const startFrac = startD.getHours() + startD.getMinutes() / 60;
                const durFrac = Math.max(0.5, (ev.end - ev.start) / 3600);
                return (
                  <div key={ev.id} onClick={() => onEditEvent(ev)} title={ev.title} style={{
                    position: 'absolute', top: startFrac * HOUR_ROW_PX + 1, left: 3, right: 3,
                    height: Math.max(18, durFrac * HOUR_ROW_PX - 2), borderRadius: 5, padding: '3px 6px', cursor: 'pointer',
                    background: `${colorFor(ev.id)}26`, color: colorFor(ev.id), borderLeft: `2px solid ${colorFor(ev.id)}`,
                    fontSize: 11, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis',
                  }}>
                    {ev.title}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function CalendarGrid({ mode, anchor, events, onSelectDay, onEditEvent }: {
  mode: CalendarViewMode; anchor: Date; events: CalendarEvent[]; onSelectDay: (d: Date) => void; onEditEvent: (e: CalendarEvent) => void;
}) {
  if (mode === 'month') return <MonthGrid anchor={anchor} events={events} onSelectDay={onSelectDay} onEditEvent={onEditEvent} />;
  return <TimeGrid anchor={anchor} mode={mode} events={events} onEditEvent={onEditEvent} />;
}
