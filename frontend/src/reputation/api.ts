/**
 * Reputation tab API client (#1446 — consolidated Reputation tab).
 *
 * Reads three self-scoped endpoints:
 *   - GET /api/societies/reputations/    — the requester's org standing (tiers only).
 *   - GET /api/societies/memberships/    — the requester's org memberships (rank titles).
 *   - GET /api/covenants/character-roles/?character_sheet= — covenant role assignments for
 *     a specific character sheet the requester currently plays.
 *
 * All three are self-only on the backend (scoped to personas/sheets the requester currently
 * plays), so there is no cross-viewer leakage risk here — this module is only ever called
 * from the Reputation tab's own-view branch.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { CharacterCovenantRole } from '@/covenants/api';
import type { components } from '@/generated/api';

export type OrganizationReputation = components['schemas']['OrganizationReputation'];
export type OrganizationMembership = components['schemas']['OrganizationMembership'];

/** GET /api/societies/reputations/ — the requester's own org standing. */
export async function fetchOrganizationReputations(): Promise<OrganizationReputation[]> {
  const res = await apiFetch('/api/societies/reputations/');
  if (!res.ok) throw new Error('Failed to load organization reputations.');
  const data = (await res.json()) as { results: OrganizationReputation[] };
  return data.results;
}

/** GET /api/societies/memberships/ — the requester's own org memberships. */
export async function fetchOrganizationMemberships(): Promise<OrganizationMembership[]> {
  const res = await apiFetch('/api/societies/memberships/');
  if (!res.ok) throw new Error('Failed to load organization memberships.');
  const data = (await res.json()) as { results: OrganizationMembership[] };
  return data.results;
}

/** GET /api/covenants/character-roles/?character_sheet={characterSheetId} */
export async function fetchCovenantRolesForSheet(
  characterSheetId: number
): Promise<CharacterCovenantRole[]> {
  const res = await apiFetch(`/api/covenants/character-roles/?character_sheet=${characterSheetId}`);
  if (!res.ok) throw new Error('Failed to load covenant roles.');
  const data = (await res.json()) as { results: CharacterCovenantRole[] };
  return data.results;
}
