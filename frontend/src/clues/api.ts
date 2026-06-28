/**
 * Clues API client (#1575) — the held-clue journal.
 *
 * Reads `/api/clues/held/` (the clues a character has discovered). Clues are private IC
 * knowledge — the endpoint only returns clues held by characters the requester plays.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type HeldClue = components['schemas']['HeldClue'];

interface PaginatedClues {
  results: HeldClue[];
}

/**
 * Fetch the held clues for one of the requester's characters (newest first).
 * GET /api/clues/held/?character_sheet={id}
 */
export async function fetchHeldClues(characterSheetId: number): Promise<HeldClue[]> {
  const res = await apiFetch(`/api/clues/held/?character_sheet=${characterSheetId}`);
  if (!res.ok) throw new Error('Failed to load clues');
  const data = (await res.json()) as PaginatedClues | HeldClue[];
  return Array.isArray(data) ? data : data.results;
}
