import { describe, expect, it } from 'vitest';
import { formatRangeLabel, rangeForView, stepAnchor } from './CalendarGrid';

// Wednesday, March 11 2026
const WED = new Date(2026, 2, 11, 10, 0, 0);

describe('rangeForView', () => {
  it('day view covers just that day', () => {
    const { start, end } = rangeForView(WED, 'day');
    expect(start.toDateString()).toBe(new Date(2026, 2, 11).toDateString());
    expect(end.toDateString()).toBe(new Date(2026, 2, 12).toDateString());
  });

  it('week view starts on Monday and spans 7 days', () => {
    const { start, end } = rangeForView(WED, 'week');
    expect(start.getDay()).toBe(1); // Monday
    expect(start.toDateString()).toBe(new Date(2026, 2, 9).toDateString());
    expect(end.toDateString()).toBe(new Date(2026, 2, 16).toDateString());
  });

  it('workweek view starts on Monday and spans 5 days', () => {
    const { start, end } = rangeForView(WED, 'workweek');
    expect(start.getDay()).toBe(1);
    expect(end.toDateString()).toBe(new Date(2026, 2, 14).toDateString());
  });

  it('month view grid starts on the Monday on/before the 1st and covers 42 days', () => {
    // March 1 2026 is a Sunday, so the grid should start Monday Feb 23
    const { start, end } = rangeForView(WED, 'month');
    expect(start.getDay()).toBe(1);
    expect(start.toDateString()).toBe(new Date(2026, 1, 23).toDateString());
    const diffDays = Math.round((end.getTime() - start.getTime()) / 86400000);
    expect(diffDays).toBe(42);
  });

  it('week that already starts on Monday stays anchored to itself', () => {
    const monday = new Date(2026, 2, 9);
    const { start } = rangeForView(monday, 'week');
    expect(start.toDateString()).toBe(monday.toDateString());
  });
});

describe('stepAnchor', () => {
  it('day mode steps by one day', () => {
    const next = stepAnchor(WED, 'day', 1);
    expect(next.toDateString()).toBe(new Date(2026, 2, 12).toDateString());
    const prev = stepAnchor(WED, 'day', -1);
    expect(prev.toDateString()).toBe(new Date(2026, 2, 10).toDateString());
  });

  it('week and workweek modes step by 7 days', () => {
    const next = stepAnchor(WED, 'week', 1);
    expect(next.toDateString()).toBe(new Date(2026, 2, 18).toDateString());
  });

  it('month mode steps by one calendar month, handling year rollover', () => {
    const dec = new Date(2026, 11, 15);
    const next = stepAnchor(dec, 'month', 1);
    expect(next.getFullYear()).toBe(2027);
    expect(next.getMonth()).toBe(0);
  });
});

describe('formatRangeLabel', () => {
  it('month label is "Month Year"', () => {
    expect(formatRangeLabel(WED, 'month')).toBe(
      WED.toLocaleDateString(undefined, { month: 'long', year: 'numeric' }),
    );
  });

  it('day label includes weekday and full date', () => {
    expect(formatRangeLabel(WED, 'day')).toBe(
      WED.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' }),
    );
  });

  it('week label spans start to end date', () => {
    const label = formatRangeLabel(WED, 'week');
    expect(label).toContain('–');
  });
});
