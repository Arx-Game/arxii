/**
 * Achievements API client (#1522).
 *
 * Currently the earned-titles read for a character's Titles tab. Plain async fetchers —
 * React Query hooks live in queries.ts.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type CharacterTitle = components['schemas']['CharacterTitle'];

interface PaginatedTitles {
  results: CharacterTitle[];
}

/**
 * Fetch a character's earned, displayable titles (newest first).
 * GET /api/achievements/character-titles/?character_sheet={id}
 *
 * The achievements API isn't globally paginated, so the list endpoint returns a bare array;
 * tolerate a paginated `{results}` shape too in case pagination is added later.
 */
export async function fetchCharacterTitles(characterSheetId: number): Promise<CharacterTitle[]> {
  const res = await apiFetch(
    `/api/achievements/character-titles/?character_sheet=${characterSheetId}`
  );
  if (!res.ok) throw new Error('Failed to load titles');
  const data = (await res.json()) as CharacterTitle[] | PaginatedTitles;
  return Array.isArray(data) ? data : data.results;
}
