/**
 * Status API client (#1446) — the qualitative status panel's own currency reads.
 *
 * Both endpoints follow the vitals-view visibility rule: staff, or an account with
 * an active tenure on the character, else 404. `fetchCharacterPurse` and
 * `fetchActionPoints` mirror `fetchCharacterVitals`'s null-on-404 behavior (see
 * `frontend/src/vitals/vitalsQueries.ts`) so the panel can simply render nothing
 * for a character the viewer doesn't own.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type CharacterPurse = components['schemas']['CharacterPurse'];
export type ActionPointPool = components['schemas']['ActionPointPool'];

/**
 * Fetch the viewer's coin purse for a character (ObjectDB pk).
 * Returns null on 401/403/404 — viewers without permission simply see no purse line.
 */
export async function fetchCharacterPurse(characterId: number): Promise<CharacterPurse | null> {
  const res = await apiFetch(`/api/currency/purse/${characterId}/`);
  if (res.status === 401 || res.status === 403 || res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to load purse for character ${characterId}`);
  return res.json();
}

/**
 * Fetch the viewer's AP pool for a character (ObjectDB pk).
 * Returns null on 401/403/404 — viewers without permission simply see no AP line.
 */
export async function fetchActionPoints(characterId: number): Promise<ActionPointPool | null> {
  const res = await apiFetch(`/api/action-points/${characterId}/`);
  if (res.status === 401 || res.status === 403 || res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to load action points for character ${characterId}`);
  return res.json();
}
