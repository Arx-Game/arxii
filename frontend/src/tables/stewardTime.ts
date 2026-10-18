/** Time left on a steward answer prompt's window (#4333 slice 4). */

/** "2 days 21 hours" until the window closes; "under an hour" near the end. */
export function timeLeft(endsAt: string, now: Date = new Date()): string {
  const ms = new Date(endsAt).getTime() - now.getTime();
  if (ms <= 0) return 'no time';
  const hours = Math.floor(ms / 3_600_000);
  const days = Math.floor(hours / 24);
  const rest = hours % 24;
  if (days === 0 && rest === 0) return 'under an hour';
  const parts: string[] = [];
  if (days) parts.push(`${days} ${days === 1 ? 'day' : 'days'}`);
  if (rest) parts.push(`${rest} ${rest === 1 ? 'hour' : 'hours'}`);
  return parts.join(' ');
}
