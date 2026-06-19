/**
 * Covenants API functions
 *
 * Covers:
 *   - CovenantViewSet  (/api/covenants/covenants/)
 *   - CharacterCovenantRoleViewSet (/api/covenants/character-roles/)
 *     including engage/disengage custom actions (Phase 7)
 *
 * Uses apiFetch from @/evennia_replacements/api.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

// ---------------------------------------------------------------------------
// Generated type aliases
// ---------------------------------------------------------------------------

export type Covenant = components['schemas']['Covenant'];
export type CharacterCovenantRole = components['schemas']['CharacterCovenantRole'];
export type CovenantRole = components['schemas']['CovenantRole'];
export type PaginatedCovenantList = components['schemas']['PaginatedCovenantList'];
export type PaginatedCharacterCovenantRoleList =
  components['schemas']['PaginatedCharacterCovenantRoleList'];
export type CovenantRank = components['schemas']['CovenantRank'];
export type CovenantRankNested = components['schemas']['CovenantRankNested'];
export type PaginatedCovenantRankList = components['schemas']['PaginatedCovenantRankList'];

/** Typed cast of the generated `{[key: string]: unknown}` viewer_capabilities block. */
export interface ViewerCapabilities {
  can_invite: boolean;
  can_kick: boolean;
  can_manage_ranks: boolean;
}

// ---------------------------------------------------------------------------
// Hand-written schema extensions (until OpenAPI regen at integration; see #518)
// ---------------------------------------------------------------------------
//
// The generated api.d.ts is a single shared file derived from ALL serializers
// across the app; regenerating it on this branch would collide with combat
// serializer changes on another branch. So these new serializer fields are
// declared by hand here, scoped to the covenants module, until the schema is
// regenerated at integration.

/** Battle-state fields added to CovenantSerializer in C1. */
export interface CovenantBattleFields {
  is_dormant: boolean;
  battle_binding: string | null;
  battle_binding_display: string;
}

/** Covenant detail payload including the C1 battle-state fields. */
export type CovenantWithBattleState = Covenant & CovenantBattleFields;

/** CovenantRole payload including the parent_role FK added in C4. */
export interface CovenantRoleWithParent extends CovenantRole {
  parent_role: number | null;
}

// ---------------------------------------------------------------------------
// Hand-written types for the powers / stand-down endpoints
// ---------------------------------------------------------------------------

/**
 * One authored CovenantRite row as returned by the powers endpoint, with the
 * per-covenant gate flags (level_met / members_present_met) the serializer adds.
 */
export interface CovenantRiteRow {
  id: number;
  ritual: number;
  covenant_type: string;
  covenant_type_display: string;
  min_covenant_level: number;
  min_members_present: number;
  granted_condition: number | null;
  base_severity: number;
  severity_per_extra_participant: number;
  // Nullable on the backend model (null=True) → serialized as number | null.
  max_severity: number | null;
  duration_rounds: number | null;
  level_met: boolean;
  members_present_met: boolean;
}

/**
 * One active membership's current passive role power, as returned by the powers
 * endpoint. Members without a woven role-thread have null capability fields.
 */
export interface RolePower {
  membership_id: number;
  character_sheet: number;
  covenant_role_id: number;
  covenant_role_name: string;
  resonance_name: string | null;
  capability_name: string | null;
  narrative_snippet: string | null;
  engaged: boolean;
}

/** Combined payload from GET /api/covenants/covenants/{id}/powers/. */
export interface CovenantPowers {
  rites: CovenantRiteRow[];
  role_powers: RolePower[];
}

/** Response from POST /api/covenants/covenants/{id}/stand_down/. */
export interface StandDownResult {
  id: number;
  is_dormant: boolean;
  battle_binding: string;
}

// ---------------------------------------------------------------------------
// URL constants
// ---------------------------------------------------------------------------

const COVENANTS_URL = '/api/covenants/covenants';
const CHARACTER_ROLES_URL = '/api/covenants/character-roles';
const ROLES_URL = '/api/covenants/roles';
const RANKS_URL = '/api/covenants/ranks';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' };
}

async function parseErrorDetail(res: Response, fallback: string): Promise<never> {
  let detail = fallback;
  try {
    const data = (await res.json()) as { detail?: string };
    if (typeof data.detail === 'string' && data.detail.trim()) {
      detail = data.detail;
    }
  } catch {
    // body wasn't JSON; keep generic
  }
  throw new Error(detail);
}

// ---------------------------------------------------------------------------
// Covenant reads
// ---------------------------------------------------------------------------

export async function getCovenants(): Promise<PaginatedCovenantList> {
  const res = await apiFetch(`${COVENANTS_URL}/`);
  if (!res.ok) throw new Error('Failed to load covenants');
  return res.json() as Promise<PaginatedCovenantList>;
}

export async function getCovenant(id: number): Promise<CovenantWithBattleState> {
  const res = await apiFetch(`${COVENANTS_URL}/${id}/`);
  if (!res.ok) throw new Error(`Failed to load covenant ${id}`);
  return res.json() as Promise<CovenantWithBattleState>;
}

// ---------------------------------------------------------------------------
// CharacterCovenantRole reads
// ---------------------------------------------------------------------------

/**
 * GET /api/covenants/character-roles/?covenant={covenantId}
 * Returns all membership rows for the given covenant.
 */
export async function getCharacterRolesForCovenant(
  covenantId: number
): Promise<PaginatedCharacterCovenantRoleList> {
  const res = await apiFetch(`${CHARACTER_ROLES_URL}/?covenant=${covenantId}`);
  if (!res.ok) throw new Error(`Failed to load members for covenant ${covenantId}`);
  return res.json() as Promise<PaginatedCharacterCovenantRoleList>;
}

// ---------------------------------------------------------------------------
// Engage / disengage mutations
// ---------------------------------------------------------------------------

/**
 * POST /api/covenants/character-roles/{id}/engage/
 * Engage a covenant role. Returns the updated CharacterCovenantRole row.
 */
export async function engageMembership(id: number): Promise<CharacterCovenantRole> {
  const res = await apiFetch(`${CHARACTER_ROLES_URL}/${id}/engage/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to engage covenant role');
  return res.json() as Promise<CharacterCovenantRole>;
}

/**
 * POST /api/covenants/character-roles/{id}/disengage/
 * Disengage a covenant role. Returns the updated CharacterCovenantRole row.
 */
export async function disengageMembership(id: number): Promise<CharacterCovenantRole> {
  const res = await apiFetch(`${CHARACTER_ROLES_URL}/${id}/disengage/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to disengage covenant role');
  return res.json() as Promise<CharacterCovenantRole>;
}

// ---------------------------------------------------------------------------
// Leave / kick mutations (exit lifecycle, #519)
// ---------------------------------------------------------------------------

/**
 * POST /api/covenants/character-roles/{id}/leave/
 * Voluntary self-leave. Returns the updated CharacterCovenantRole row.
 */
export async function leaveMembership(id: number): Promise<CharacterCovenantRole> {
  const res = await apiFetch(`${CHARACTER_ROLES_URL}/${id}/leave/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to leave covenant');
  return res.json() as Promise<CharacterCovenantRole>;
}

/**
 * POST /api/covenants/character-roles/{id}/kick/
 * A leader removes a non-leader member. Returns the updated target row.
 */
export async function kickMember(id: number): Promise<CharacterCovenantRole> {
  const res = await apiFetch(`${CHARACTER_ROLES_URL}/${id}/kick/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to remove member');
  return res.json() as Promise<CharacterCovenantRole>;
}

// ---------------------------------------------------------------------------
// Powers read
// ---------------------------------------------------------------------------

/**
 * GET /api/covenants/covenants/{id}/powers/
 * Returns the covenant's authored rites (with gate flags) and per-member
 * passive role powers in one payload.
 */
export async function getCovenantPowers(covenantId: number): Promise<CovenantPowers> {
  const res = await apiFetch(`${COVENANTS_URL}/${covenantId}/powers/`);
  if (!res.ok) throw new Error(`Failed to load powers for covenant ${covenantId}`);
  return res.json() as Promise<CovenantPowers>;
}

// ---------------------------------------------------------------------------
// Stand-down mutation (battle covenants)
// ---------------------------------------------------------------------------

/**
 * POST /api/covenants/covenants/{id}/stand_down/
 * Stand a raised battle covenant down to dormant. Returns its new battle state.
 */
export async function standDownCovenant(covenantId: number): Promise<StandDownResult> {
  const res = await apiFetch(`${COVENANTS_URL}/${covenantId}/stand_down/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to stand down covenant');
  return res.json() as Promise<StandDownResult>;
}

// ---------------------------------------------------------------------------
// Promotion mutation
// ---------------------------------------------------------------------------

/**
 * POST /api/covenants/character-roles/{id}/promote/
 * Promote a membership into one of its current role's sub-roles. Returns the
 * new CharacterCovenantRole row.
 */
export async function promoteMembership(
  membershipId: number,
  targetSubroleId: number
): Promise<CharacterCovenantRole> {
  const res = await apiFetch(`${CHARACTER_ROLES_URL}/${membershipId}/promote/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({ target_subrole: targetSubroleId }),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to promote covenant role');
  return res.json() as Promise<CharacterCovenantRole>;
}

// ---------------------------------------------------------------------------
// CovenantRole lookup (unpaginated)
// ---------------------------------------------------------------------------

/**
 * GET /api/covenants/roles/?covenant_type=&parent_role=
 * Returns the (unpaginated) CovenantRole lookup list. Pass `parent_role` to
 * fetch a role's sub-roles for the promotion picker.
 */
export async function getCovenantRoles(params: {
  covenant_type?: string;
  parent_role?: number;
}): Promise<CovenantRoleWithParent[]> {
  const search = new URLSearchParams();
  if (params.covenant_type != null) search.set('covenant_type', params.covenant_type);
  if (params.parent_role != null) search.set('parent_role', String(params.parent_role));
  const query = search.toString();
  const res = await apiFetch(`${ROLES_URL}/${query ? `?${query}` : ''}`);
  if (!res.ok) throw new Error('Failed to load covenant roles');
  return res.json() as Promise<CovenantRoleWithParent[]>;
}

// ---------------------------------------------------------------------------
// Rank reads
// ---------------------------------------------------------------------------

/**
 * GET /api/covenants/ranks/?covenant={covenantId}
 * Returns all ranks for the given covenant, ordered by tier.
 */
export async function getCovenantRanksForCovenant(
  covenantId: number
): Promise<PaginatedCovenantRankList> {
  const res = await apiFetch(`${RANKS_URL}/?covenant=${covenantId}`);
  if (!res.ok) throw new Error(`Failed to load ranks for covenant ${covenantId}`);
  return res.json() as Promise<PaginatedCovenantRankList>;
}

// ---------------------------------------------------------------------------
// Rank mutations
// ---------------------------------------------------------------------------

/**
 * POST /api/covenants/ranks/
 * Create a new rank for the given covenant.
 */
export async function createCovenantRank(data: {
  covenant: number;
  name: string;
  tier: number;
  description?: string;
  can_invite?: boolean;
  can_kick?: boolean;
  can_manage_ranks?: boolean;
}): Promise<CovenantRank> {
  const res = await apiFetch(`${RANKS_URL}/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to create rank');
  return res.json() as Promise<CovenantRank>;
}

/**
 * PATCH /api/covenants/ranks/{id}/
 * Partial-update a rank (rename, toggle capability flags).
 */
export async function updateCovenantRank(
  id: number,
  data: Partial<{
    name: string;
    description: string;
    can_invite: boolean;
    can_kick: boolean;
    can_manage_ranks: boolean;
  }>
): Promise<CovenantRank> {
  const res = await apiFetch(`${RANKS_URL}/${id}/`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to update rank');
  return res.json() as Promise<CovenantRank>;
}

/**
 * DELETE /api/covenants/ranks/{id}/
 * Delete a rank, reassigning its members to `reassignTo`.
 */
export async function deleteCovenantRank(id: number, reassignTo: number): Promise<void> {
  const res = await apiFetch(`${RANKS_URL}/${id}/`, {
    method: 'DELETE',
    headers: jsonHeaders(),
    body: JSON.stringify({ reassign_to: reassignTo }),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to delete rank');
}

/**
 * POST /api/covenants/ranks/{rankId}/assign-member/
 * Assign a member to this rank.
 */
export async function assignMemberToRank(
  rankId: number,
  membershipId: number
): Promise<CharacterCovenantRole> {
  const res = await apiFetch(`${RANKS_URL}/${rankId}/assign-member/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({ membership: membershipId }),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to assign member to rank');
  return res.json() as Promise<CharacterCovenantRole>;
}

/**
 * POST /api/covenants/ranks/reorder/
 * Reorder all ranks for a covenant.
 */
export async function reorderRanks(
  covenantId: number,
  orderedRankIds: number[]
): Promise<PaginatedCovenantRankList> {
  const res = await apiFetch(`${RANKS_URL}/reorder/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({ covenant: covenantId, ordered_rank_ids: orderedRankIds }),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to reorder ranks');
  return res.json() as Promise<PaginatedCovenantRankList>;
}
