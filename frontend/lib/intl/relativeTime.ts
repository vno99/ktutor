/*
 * relativeTime.ts — pure formatter for ``last_activity_at`` (s19, ADR 015 § Decision 5).
 *
 * The plan deliberately defers a shared <RelativeTime> component to
 * a later story (s22 or 3+ stories consuming it). For s19 the formatter
 * is a 10-line pure helper. ``Intl.RelativeTimeFormat`` returns
 * localised strings such as "il y a 2 heures" (fr) / "2 hours ago"
 * (en) / "vor 2 Stunden" (de) — driven by the active next-intl locale.
 *
 * The 7-day fall-through boundary is a UX choice: after a week the
 * exact time stops being useful, and a date is more informative
 * ("12 sept." vs "il y a 7 jours"). The boundary lives in the
 * formatter so the callers stay simple.
 *
 * The formatter is pure: same input, same output. The current time
 * is injected by the caller (``now`` parameter) so the unit tests
 * are deterministic.
 */

const SECOND = 1_000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEK = 7 * DAY;

/**
 * Format a past instant as a relative-time string in the given locale.
 *
 * @param iso  ISO 8601 instant in the past.
 * @param locale  BCP 47 locale tag (e.g. ``"fr"``, ``"en"``).
 * @param now  Reference instant (default: ``Date.now()``). Tests pass
 *             a fixed value to keep the output deterministic.
 * @returns A localised relative-time string, or a short date if the
 *          delta is greater than a week, or ``""`` if the input is
 *          unparseable.
 */
export function formatRelativeTime(
  iso: string,
  locale: string,
  now: number = Date.now(),
): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const delta = now - then;
  if (delta < 0) return ''; // future timestamps — caller will deal with it
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  if (delta < MINUTE) {
    return rtf.format(-Math.round(delta / SECOND), 'second');
  }
  if (delta < HOUR) {
    return rtf.format(-Math.round(delta / MINUTE), 'minute');
  }
  if (delta < DAY) {
    return rtf.format(-Math.round(delta / HOUR), 'hour');
  }
  if (delta < WEEK) {
    return rtf.format(-Math.round(delta / DAY), 'day');
  }
  // After a week the exact relative time is noise — fall back to a
  // short, locale-aware date.
  return new Intl.DateTimeFormat(locale, {
    day: 'numeric',
    month: 'short',
  }).format(new Date(iso));
}
