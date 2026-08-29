/**
 * Clues API client (#1575) — the held-clue journal, plus the #3432 authoring dispatch.
 *
 * Reads `/api/clues/held/` (the clues a character has discovered). Clues are private IC
 * knowledge — the endpoint only returns clues held by characters the requester plays.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';
import { dispatchCanvasAction, type DispatchResult } from '@/map-canvas/dispatch';

export type HeldClue = components['schemas']['HeldClue'];

export type { DispatchResult };

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

/**
 * Dispatch `author_clue` (#3432, SENIOR-GM/staff clue authoring) for `characterId`. Thin
 * wrapper over the shared REGISTRY dispatch seam (`dispatchWorldBuilder`'s sibling) — kept
 * outside `WorldBuilderActionKey` since `AuthorClueDialog` is also mounted from the
 * (non-world-builder) `StaffSecretsPanel`. On success, `data.slug` is the new clue's slug.
 */
export function authorClue(
  characterId: number,
  kwargs: Record<string, unknown>
): Promise<DispatchResult> {
  return dispatchCanvasAction(characterId, 'author_clue', kwargs);
}
