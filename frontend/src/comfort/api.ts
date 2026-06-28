/**
 * Comfort API client (#1522).
 *
 * Plain async fetchers — React Query hooks live in queries.ts. Mirrors the weather/conditions
 * read pattern, but comfort is personal: a thin GET that returns how uncomfortable the active
 * character is in their current room, and why.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type CharacterComfort = components['schemas']['CharacterComfort'];

/**
 * Fetch the per-character comfort readout.
 * GET /api/locations/comfort/?character_id={characterId}
 */
export async function fetchCharacterComfort(characterId: number): Promise<CharacterComfort> {
  const res = await apiFetch(`/api/locations/comfort/?character_id=${characterId}`);
  if (!res.ok) throw new Error('Failed to load comfort');
  return res.json() as Promise<CharacterComfort>;
}
