import { describe, it, expect } from 'vitest';
import { formatRelativeTime } from './relativeTime';

/*
 * Unit tests for the relative-time formatter (s19, ADR 015 § Decision 5).
 *
 * The formatter is pure: the ``now`` parameter is injected so the
 * tests don't depend on wall-clock time. The thresholds come from
 * the implementation (SECOND, MINUTE, HOUR, DAY, WEEK).
 *
 * Locale behaviour is delegated to ``Intl.RelativeTimeFormat`` — we
 * assert the French/English shape (presence of "il y a" / "ago")
 * rather than the exact text, so the tests survive ICU data updates.
 */

const NOW = Date.parse('2026-09-05T12:00:00Z');

describe('formatRelativeTime', () => {
  it('returns an empty string for an unparseable input', () => {
    expect(formatRelativeTime('not-a-date', 'fr', NOW)).toBe('');
  });

  it('returns an empty string for a future timestamp', () => {
    const future = new Date(NOW + 60_000).toISOString();
    expect(formatRelativeTime(future, 'fr', NOW)).toBe('');
  });

  it('formats a sub-minute delta in seconds (fr)', () => {
    const iso = new Date(NOW - 30 * 1000).toISOString();
    const out = formatRelativeTime(iso, 'fr', NOW);
    expect(out).toMatch(/30\s+secondes/);
  });

  it('formats a sub-hour delta in minutes (fr)', () => {
    const iso = new Date(NOW - 5 * 60 * 1000).toISOString();
    const out = formatRelativeTime(iso, 'fr', NOW);
    expect(out).toMatch(/5\s+minutes/);
  });

  it('formats a sub-day delta in hours (fr)', () => {
    const iso = new Date(NOW - 3 * 60 * 60 * 1000).toISOString();
    const out = formatRelativeTime(iso, 'fr', NOW);
    expect(out).toMatch(/3\s+heures/);
  });

  it('formats a sub-week delta in days (fr)', () => {
    // With ``numeric: 'auto'`` Intl.RelativeTimeFormat maps ``-2 days``
    // to "avant-hier" in fr (and "the day before yesterday" in en).
    // 3+ days falls through to a numeric "N jours".
    const iso = new Date(NOW - 4 * 24 * 60 * 60 * 1000).toISOString();
    const out = formatRelativeTime(iso, 'fr', NOW);
    expect(out).toMatch(/4\s+jours/);
  });

  it('maps -1 day to the locale "yesterday" word (numeric: auto)', () => {
    const iso = new Date(NOW - 24 * 60 * 60 * 1000).toISOString();
    expect(formatRelativeTime(iso, 'fr', NOW)).toBe('hier');
    expect(formatRelativeTime(iso, 'en', NOW)).toBe('yesterday');
  });

  it('falls back to a short date after a week (fr)', () => {
    const iso = new Date(NOW - 10 * 24 * 60 * 60 * 1000).toISOString();
    const out = formatRelativeTime(iso, 'fr', NOW);
    // Should not contain the relative-time "il y a" — should be a date.
    expect(out).not.toMatch(/il y a/);
    expect(out.length).toBeGreaterThan(0);
  });

  it('produces an English-shaped string for the en locale', () => {
    const iso = new Date(NOW - 2 * 60 * 60 * 1000).toISOString();
    const out = formatRelativeTime(iso, 'en', NOW);
    expect(out).toMatch(/2\s+hours?\s+ago/);
  });
});
