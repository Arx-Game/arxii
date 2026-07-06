/**
 * Convert an Evennia dbref like ``#42`` to the numeric ObjectDB pk used by
 * REST endpoints and the websocket action dispatcher's ``<name>_id`` kwargs.
 *
 * Falls back to ``0`` when parsing fails — callers render their own
 * "unavailable" state for a bogus id rather than throwing inside a click
 * handler or a dispatch call.
 */
export function dbrefToId(dbref: string): number {
  const stripped = dbref.startsWith('#') ? dbref.slice(1) : dbref;
  const parsed = Number.parseInt(stripped, 10);
  return Number.isFinite(parsed) ? parsed : 0;
}
