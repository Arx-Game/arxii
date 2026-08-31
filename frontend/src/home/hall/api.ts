/**
 * The Hall (#3412 slice 2) — fetchers with no existing frontend home.
 * `GET /api/clock/` has never had a frontend consumer before the Hall's
 * calendar plate (`world/game_clock/views.py::ClockViewSet.list`).
 *
 * The GM-profile fetchers below (#3478 task 5) back the Hall's GM slot:
 * minting the account's own GM/Staff character, and reading/editing its
 * operational info (`contact_times`/`ooc_info`).
 */

import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import type { ClockState, GMProfileMine } from './types';

export async function fetchClockState(): Promise<ClockState> {
  const res = await apiFetch('/api/clock/');
  if (!res.ok) throw new Error('Failed to load the clock');
  return res.json();
}

/**
 * Mint the account's own GM/Staff character (#3478) — role gating
 * (staff -> `StaffCharacter`, approved GM -> `GMCharacter`, anyone else
 * refused) is entirely server-side (`mint_gm_character`). This endpoint
 * replaced world-builder's `mint-builder-character` (#3283); the
 * world-builder page no longer mints — it points a characterless GM at
 * this Hall flow instead (`WorldBuilderPage`'s no-actor banner, #3478 Task 6).
 */
export async function mintGMCharacter(
  name: string
): Promise<{ character_id: number; name: string }> {
  const res = await apiFetch('/api/gm/profiles/character/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to create the GM character.');
  return (await res.json()) as { character_id: number; name: string };
}

/**
 * GET the requesting account's own GM profile (#3478 Task 1). 404s for a
 * staff account with no approved `GMProfile` row — callers treat that as
 * "no editable GM profile," not an error to surface (see `GMSlot`, which
 * hides its edit affordance rather than rendering the 404).
 */
export async function fetchGMProfileMine(): Promise<GMProfileMine> {
  const res = await apiFetch('/api/gm/profiles/mine/');
  if (!res.ok) await throwApiError(res, 'Failed to load your GM profile.');
  return (await res.json()) as GMProfileMine;
}

/**
 * PATCH the requesting account's own GM profile. Only `contact_times`/
 * `ooc_info` are writable — `level` is read-only server-side (Task 1) and
 * silently dropped by DRF if sent.
 */
export async function updateGMProfileMine(
  data: Partial<Pick<GMProfileMine, 'contact_times' | 'ooc_info'>>
): Promise<GMProfileMine> {
  const res = await apiFetch('/api/gm/profiles/mine/', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) await throwApiError(res, 'Failed to save your GM profile.');
  return (await res.json()) as GMProfileMine;
}
