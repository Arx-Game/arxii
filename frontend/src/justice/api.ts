/**
 * Justice API client (#1765) — the crime tab's warrant rows.
 *
 * Reads `/api/justice/heat/` — where the viewer's active persona is wanted, and for what.
 * Self-only: the backend scopes to the requesting account's own active persona and returns
 * tiers, never raw heat numbers.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
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

export interface WantedRow {
  persona_name: string;
  tier: string;
  society_name: string;
  crimes: string[];
}

/** The public wanted board for an area (#1826) — tiers, never numbers. */
export async function fetchWantedList(areaId: number): Promise<WantedRow[]> {
  const res = await apiFetch(`/api/justice/wanted/?area=${areaId}`);
  if (!res.ok) await throwApiError(res, 'Failed to load the wanted board');
  const data = (await res.json()) as { wanted: WantedRow[] };
  return data.wanted;
}

/** Declare (or end) lying low in an area (#1826). */
export async function postLieLow(
  viewerEntryId: number,
  areaId: number,
  end = false
): Promise<{ active: boolean }> {
  const res = await apiFetch('/api/justice/lie-low/', {
    method: 'POST',
    body: JSON.stringify({ viewer: viewerEntryId, area: areaId, end }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to change lie-low state');
  return res.json();
}

export interface BribeOutcome {
  success_level: number;
  cleared_pct: number;
  coin_spent: number;
  crime_minted: boolean;
}

/** Bribe the hunters in an area; pass preview to fetch the cost only (#1826). */
export async function postBribe(
  viewerEntryId: number,
  areaId: number,
  preview = false
): Promise<BribeOutcome | { cost_coppers: number }> {
  const res = await apiFetch('/api/justice/bribe/', {
    method: 'POST',
    body: JSON.stringify({ viewer: viewerEntryId, area: areaId, preview }),
  });
  if (!res.ok) await throwApiError(res, 'The bribe approach failed');
  return res.json();
}
