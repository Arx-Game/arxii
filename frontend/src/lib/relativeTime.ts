/**
 * Relative time formatting using native Intl.RelativeTimeFormat.
 * No external dependency required.
 */

const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

const CUTOFFS: [number, Intl.RelativeTimeFormatUnit][] = [
  [60, 'second'],
  [3600, 'minute'],
  [86400, 'hour'],
  [86400 * 7, 'day'],
  [86400 * 30, 'week'],
  [86400 * 365, 'month'],
  [Infinity, 'year'],
];

const DIVISORS: Record<string, number> = {
  second: 1,
  minute: 60,
  hour: 3600,
  day: 86400,
  week: 86400 * 7,
  month: 86400 * 30,
  year: 86400 * 365,
};

/**
 * Format a date as a human-readable relative time string, e.g. "3 minutes ago".
 */
export function formatRelativeTime(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  const deltaSeconds = Math.round((d.getTime() - Date.now()) / 1000);
  const absDelta = Math.abs(deltaSeconds);

  for (const [cutoff, unit] of CUTOFFS) {
    if (absDelta < cutoff) {
      const divisor = DIVISORS[unit] ?? 1;
      return rtf.format(Math.round(deltaSeconds / divisor), unit);
    }
  }

  return rtf.format(Math.round(deltaSeconds / DIVISORS.year), 'year');
}
