/**
 * Combat API client functions.
 *
 * Plain async functions — not hooks. React Query hooks live in queries.ts.
 * Phase 7 of the unified-combat-ui plan.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import type { components } from '@/generated/api';
import type { PowerLedger } from '@/magic/types';
import type {
  AvailableCombo,
  DispatchActionRequest,
  DispatchResult,
  EncounterDetail,
  EncounterListItem,
} from './types';

// ---------------------------------------------------------------------------
// Re-exported generated types for consequence outcomes
// ---------------------------------------------------------------------------

export type ConsequenceOutcome = components['schemas']['ConsequenceOutcome'];
export type ConsequenceOutcomeModifier = components['schemas']['ConsequenceOutcomeModifier'];

/** One row in the duel-challenge inbox (GET /api/combat/duel-challenges/). */
export type DuelChallenge = components['schemas']['DuelChallenge'];

/** Direction of a duel challenge relative to the requesting player. */
export type DuelChallengeRole = 'incoming' | 'outgoing';

/**
 * A single row in the outcome_display roulette wheel.
 * The backend annotates get_outcome_display with @extend_schema_field
 * (OutcomeDisplayRowSerializer), so this is a direct re-export (#2423).
 */
export type OutcomeDisplayRow = components['schemas']['OutcomeDisplayRow'];

// ---------------------------------------------------------------------------
// Encounter
// ---------------------------------------------------------------------------

/**
 * Fetch the full encounter state.
 * GET /api/combat/{encounterId}/
 */
export async function fetchEncounter(encounterId: number): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/`);
  if (!res.ok) throw new Error('Failed to load encounter');
  return res.json() as Promise<EncounterDetail>;
}

/**
 * List encounters filtered by scene, ordered most-recent first.
 * GET /api/combat/?scene=<sceneId>
 *
 * Returns the list of encounter summaries for the given scene.
 * CombatEncounterViewSet.get_queryset() already applies order_by("-created_at"),
 * so the first non-completed result is deterministically the most-recent one.
 * The caller picks the first non-completed encounter from this ordered list.
 */
export async function fetchEncountersForScene(sceneId: number): Promise<EncounterListItem[]> {
  const res = await apiFetch(`/api/combat/?scene=${sceneId}`);
  if (!res.ok) throw new Error('Failed to load encounters for scene');
  const data = (await res.json()) as { results?: EncounterListItem[]; count?: number };
  return data.results ?? [];
}

// ---------------------------------------------------------------------------
// Duel-challenge inbox
// ---------------------------------------------------------------------------

/**
 * List the requesting player's PENDING duel challenges.
 * GET /api/combat/duel-challenges/[?role=incoming|outgoing]
 *
 * Scoped server-side to the caller's played characters. Returns the results
 * array from the paginated response.
 */
export async function fetchDuelChallengeInbox(role?: DuelChallengeRole): Promise<DuelChallenge[]> {
  const url = role ? `/api/combat/duel-challenges/?role=${role}` : '/api/combat/duel-challenges/';
  const res = await apiFetch(url);
  if (!res.ok) throw new Error('Failed to load duel challenges');
  const data = (await res.json()) as { results?: DuelChallenge[]; count?: number };
  return data.results ?? [];
}

// ---------------------------------------------------------------------------
// Available combos
//
// The generated schema types the available_combos response as EncounterDetail,
// but the actual payload from the backend is a list of combo descriptors.
// We type the response locally as AvailableCombo[] to match the actual payload.
// ---------------------------------------------------------------------------

/**
 * Fetch available combo upgrades for the encounter.
 * GET /api/combat/{encounterId}/available_combos/
 */
export async function fetchAvailableCombos(encounterId: number): Promise<AvailableCombo[]> {
  const res = await apiFetch(`/api/combat/${encounterId}/available_combos/`);
  if (!res.ok) throw new Error('Failed to load available combos');
  return res.json() as Promise<AvailableCombo[]>;
}

// ---------------------------------------------------------------------------
// Upgrade combo
// ---------------------------------------------------------------------------

/**
 * Upgrade an action to a combo.
 * POST /api/combat/{encounterId}/upgrade_combo/
 * Body: { combo_id: number }
 */
export async function postUpgradeCombo(
  encounterId: number,
  comboId: number
): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/upgrade_combo/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ combo_id: comboId }),
  });
  if (!res.ok) throw new Error('Failed to upgrade combo');
  return res.json() as Promise<EncounterDetail>;
}

// ---------------------------------------------------------------------------
// Join encounter (player self-join)
// ---------------------------------------------------------------------------

/**
 * Player self-joins an Open Encounter.
 * POST /api/combat/{encounterId}/join/
 * Body: { character_sheet_id: number }
 * 400 if already joined; 403 if not in encounter room.
 */
export async function postJoin(
  encounterId: number,
  characterSheetId: number
): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/join/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ character_sheet_id: characterSheetId }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to join encounter');
  return res.json() as Promise<EncounterDetail>;
}

// ---------------------------------------------------------------------------
// Leave encounter (player voluntary exit)
// ---------------------------------------------------------------------------

/**
 * Player voluntarily leaves an Open Encounter between rounds.
 * POST /api/combat/{encounterId}/leave/
 * No body required. 400 if not between_rounds; 403 non-participant.
 */
export async function postLeave(encounterId: number): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/leave/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) await throwApiError(res, 'Failed to leave encounter');
  return res.json() as Promise<EncounterDetail>;
}

// ---------------------------------------------------------------------------
// Flee declaration
// ---------------------------------------------------------------------------

/**
 * Declare intent to flee this round.
 * POST /api/combat/{encounterId}/flee/
 * No body required. 400 outside declaring phase; 403 non-participant.
 */
export async function postFlee(encounterId: number): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/flee/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) await throwApiError(res, 'Failed to declare flee');
  return res.json() as Promise<EncounterDetail>;
}

// ---------------------------------------------------------------------------
// End encounter (GM only)
// ---------------------------------------------------------------------------

/**
 * End the encounter early, recording the "abandoned" outcome (#876).
 * POST /api/combat/{encounterId}/end/
 * No body required. 400 if already completed; 403 non-GM.
 */
export async function postEndEncounter(encounterId: number): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/end/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) await throwApiError(res, 'Failed to end encounter');
  return res.json() as Promise<EncounterDetail>;
}

// ---------------------------------------------------------------------------
// Cover declaration
// ---------------------------------------------------------------------------

/**
 * Declare cover for an ally participant.
 * POST /api/combat/{encounterId}/cover/
 * Body: { ally_participant_id: number }
 * 400 invalid (self/inactive); 404 foreign ally; 403 non-participant.
 */
export async function postCover(
  encounterId: number,
  allyParticipantId: number
): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/cover/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ally_participant_id: allyParticipantId }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to declare cover');
  return res.json() as Promise<EncounterDetail>;
}

// ---------------------------------------------------------------------------
// Dispatch player action
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Outcome details
// ---------------------------------------------------------------------------

export interface OutcomeEffectRow {
  kind: string;
  label: string;
  // True for load-bearing outcomes (KO/death/defeat); the detail panel
  // highlights these. (#996)
  is_critical: boolean;
  deep_link: { modal: string; id: number } | null;
}

export interface ActionOutcomeDetail {
  action_interaction_id: number;
  effects: OutcomeEffectRow[];
  power_ledger?: PowerLedger | null;
  // Clash contributions only (null for non-clash outcomes). `power` mirrors the
  // power_ledger total and is gated to caster/staff; strain_committed and
  // progress_delta tell the strain→power→progress story and are not gated.
  strain_committed?: number | null;
  power?: number | null;
  progress_delta?: number | null;
}

/**
 * Fetch outcome details for a set of ACTION Interactions (lazy).
 * GET /api/combat/action-outcome-details/?action_interaction_ids=N,M,...
 */
export async function fetchOutcomeDetails(
  actionInteractionIds: number[]
): Promise<ActionOutcomeDetail[]> {
  const ids = actionInteractionIds.join(',');
  const res = await apiFetch(`/api/combat/action-outcome-details/?action_interaction_ids=${ids}`);
  if (!res.ok) throw new Error('Failed to load outcome details');
  return res.json() as Promise<ActionOutcomeDetail[]>;
}

// ---------------------------------------------------------------------------
// Consequence outcomes
// ---------------------------------------------------------------------------

export interface ConsequenceOutcomesParams {
  character?: number;
  pool?: number;
  encounter?: number;
  created_after?: string;
  created_before?: string;
  page?: number;
  page_size?: number;
}

/**
 * Fetch a paginated list of ConsequenceOutcome records.
 * GET /api/checks/consequence-outcomes/
 *
 * Returns the results array from the paginated response.
 * Supports filtering by character, pool, and time range.
 */
export async function fetchConsequenceOutcomes(
  params: ConsequenceOutcomesParams = {}
): Promise<ConsequenceOutcome[]> {
  const qs = new URLSearchParams();
  if (params.character !== undefined) qs.set('character', String(params.character));
  if (params.pool !== undefined) qs.set('pool', String(params.pool));
  if (params.encounter !== undefined) qs.set('encounter', String(params.encounter));
  if (params.created_after !== undefined) qs.set('created_after', params.created_after);
  if (params.created_before !== undefined) qs.set('created_before', params.created_before);
  if (params.page !== undefined) qs.set('page', String(params.page));
  if (params.page_size !== undefined) qs.set('page_size', String(params.page_size));

  const query = qs.toString();
  const url = query
    ? `/api/checks/consequence-outcomes/?${query}`
    : '/api/checks/consequence-outcomes/';

  const res = await apiFetch(url);
  if (!res.ok) throw new Error('Failed to load consequence outcomes');
  const data = (await res.json()) as { results?: ConsequenceOutcome[]; count?: number };
  return data.results ?? [];
}

/**
 * Dispatch a player action — the unified write path for all action types.
 * POST /api/actions/characters/{characterId}/dispatch/
 */
export async function postDispatchAction(
  characterId: number,
  body: DispatchActionRequest
): Promise<DispatchResult> {
  const res = await apiFetch(`/api/actions/characters/${characterId}/dispatch/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) await throwApiError(res, 'Failed to dispatch action');
  return res.json() as Promise<DispatchResult>;
}
