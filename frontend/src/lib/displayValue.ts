/**
 * Render an unknown value as display text without ever producing "[object Object]".
 *
 * `String(someObject)` yields the literal string "[object Object]", which reaches
 * the UI as noise. Flow-builder and predicate parameters are typed `unknown` and
 * genuinely can be dicts, so this is a real display path, not a theoretical one.
 * Objects and arrays are JSON-encoded instead; null and undefined collapse to
 * `empty`.
 */
export function toDisplayString(value: unknown, empty = ''): string {
  if (value === undefined || value === null) return empty;
  if (typeof value === 'object') return JSON.stringify(value) ?? empty;
  return String(value);
}
