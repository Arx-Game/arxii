/**
 * Weather API client (#1522).
 *
 * Plain async fetchers — React Query hooks live in queries.ts. Mirrors the clock/conditions
 * read pattern: a thin GET that returns the IC time + the weather holding at a room.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type WeatherConditions = components['schemas']['Conditions'];

/**
 * Fetch the IC time + weather at a room.
 * GET /api/weather/conditions/?room_id={roomId}
 *
 * With `roomId` null the server resolves the acting character's room instead
 * (#3539: the Hall's Time plate has no live session room); `entryId` names
 * the tab's browsing identity (#3479) for that resolution, falling back to
 * the account's durable selection when omitted. The server ignores
 * `entry_id` whenever `room_id` is supplied, so it is only sent on the
 * no-room path. A 404 there is an ordinary answer (no resolvable character,
 * or the character stands nowhere), so it resolves to null rather than
 * throwing (a throw would put React Query into retry/error churn over a
 * non-error).
 */
export async function fetchWeatherConditions(
  roomId: number | null,
  entryId?: number | null
): Promise<WeatherConditions | null> {
  let url = '/api/weather/conditions/';
  if (roomId != null) {
    url += `?room_id=${roomId}`;
  } else if (entryId != null) {
    url += `?entry_id=${entryId}`;
  }
  const res = await apiFetch(url);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Failed to load weather conditions');
  return res.json() as Promise<WeatherConditions>;
}
