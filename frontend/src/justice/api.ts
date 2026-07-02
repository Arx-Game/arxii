/**
 * Justice API client (#1765) — the crime tab's warrant rows.
 *
 * Reads `/api/justice/heat/` — where the viewer's active persona is wanted, and for what.
 * Self-only: the backend scopes to the requesting account's own active persona and returns
 * tiers, never raw heat numbers.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type PersonaHeatRow = components['schemas']['PersonaHeat'];

interface PaginatedHeat {
  results: PersonaHeatRow[];
}

/**
 * Fetch the viewer's own warrant rows (their active persona's pursuit picture).
 * GET /api/justice/heat/?viewer={rosterEntryId}
 */
export async function fetchPersonaHeat(viewerEntryId: number): Promise<PersonaHeatRow[]> {
  const res = await apiFetch(`/api/justice/heat/?viewer=${viewerEntryId}`);
  if (!res.ok) throw new Error('Failed to load crime records');
  const data = (await res.json()) as PaginatedHeat | PersonaHeatRow[];
  return Array.isArray(data) ? data : data.results;
}
