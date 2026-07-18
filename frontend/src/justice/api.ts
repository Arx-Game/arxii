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
  persona_id: number;
  persona_name: string;
  tier: string;
  tier_label: string;
  society_name: string;
  crimes: string[];
}

/** An awaiting-trial captive in the area — the help-the-accused discovery seam (#2378). */
export interface HeldRow {
  case_id: number;
  persona_name: string;
}

export interface WantedBoardData {
  wanted: WantedRow[];
  held: HeldRow[];
  /** Whether the viewer holds pardon power here (magistrate office / org leadership). */
  viewer_can_pardon: boolean;
}

/** The public wanted board for an area (#1826) — tiers, never numbers. */
export async function fetchWantedList(
  areaId: number,
  viewerEntryId?: number | null
): Promise<WantedBoardData> {
  const viewer = viewerEntryId != null ? `&viewer=${viewerEntryId}` : '';
  const res = await apiFetch(`/api/justice/wanted/?area=${areaId}${viewer}`);
  if (!res.ok) await throwApiError(res, 'Failed to load the wanted board');
  return (await res.json()) as WantedBoardData;
}

/** The captive's own case picture (#2378). */
export interface MyCase {
  id: number;
  area_name: string;
  society_name: string;
  opened_at: string;
  evidence_total: number;
  release_threshold: number;
  failed_outs: number;
}

/** GET /api/justice/my-case/ — null when the viewer has no open case. */
export async function fetchMyCase(viewerEntryId: number): Promise<MyCase | null> {
  const res = await apiFetch(`/api/justice/my-case/?viewer=${viewerEntryId}`);
  if (!res.ok) await throwApiError(res, 'Failed to load your case');
  const data = (await res.json()) as { case: MyCase | null };
  return data.case;
}

/** Submit exculpatory evidence for a held friend — help only, never hurt (#2378). */
export async function postEvidence(
  viewerEntryId: number,
  caseId: number,
  manufactured: boolean
): Promise<{ status: string; evidence_total: number }> {
  const res = await apiFetch('/api/justice/cases/evidence/', {
    method: 'POST',
    body: JSON.stringify({ viewer: viewerEntryId, case: caseId, manufactured }),
  });
  if (!res.ok) await throwApiError(res, 'The evidence submission failed');
  return res.json();
}

export interface TrialOutcome {
  verdict: string;
  sentence_kind: string | null;
  sentence_amount: number;
}

/** The captive calls their moment before the NPC judge (#2378). */
export async function postTrial(viewerEntryId: number, caseId: number): Promise<TrialOutcome> {
  const res = await apiFetch('/api/justice/cases/trial/', {
    method: 'POST',
    body: JSON.stringify({ viewer: viewerEntryId, case: caseId }),
  });
  if (!res.ok) await throwApiError(res, 'The trial could not proceed');
  return res.json();
}

/** A lord's grant: clear a persona's heat with the enforcing society (#1826). */
export async function postPardon(
  viewerEntryId: number,
  areaId: number,
  targetPersonaId: number
): Promise<{ heat_cleared: number }> {
  const res = await apiFetch('/api/justice/pardon/', {
    method: 'POST',
    body: JSON.stringify({ viewer: viewerEntryId, area: areaId, target_persona: targetPersonaId }),
  });
  if (!res.ok) await throwApiError(res, 'The pardon was refused');
  return res.json();
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
