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
 */
export async function fetchWeatherConditions(roomId: number): Promise<WeatherConditions> {
  const res = await apiFetch(`/api/weather/conditions/?room_id=${roomId}`);
  if (!res.ok) throw new Error('Failed to load weather conditions');
  return res.json() as Promise<WeatherConditions>;
}
