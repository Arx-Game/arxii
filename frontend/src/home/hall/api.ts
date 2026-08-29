/**
 * The Hall (#3412 slice 2) — fetchers with no existing frontend home.
 * `GET /api/clock/` has never had a frontend consumer before the Hall's
 * calendar plate (`world/game_clock/views.py::ClockViewSet.list`).
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { ClockState } from './types';

export async function fetchClockState(): Promise<ClockState> {
  const res = await apiFetch('/api/clock/');
  if (!res.ok) throw new Error('Failed to load the clock');
  return res.json();
}
