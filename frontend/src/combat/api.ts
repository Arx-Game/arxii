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
  RoundCombo,
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

/** One row of the ThreatPool catalog (GET /api/combat/threat-pools/, #3067). */
export type ThreatPool = components['schemas']['ThreatPool'];

/**
 * List authored ThreatPools (NPC move-sets), optionally name-filtered — the
 * GM add-opponent picker's data source (#3067).
 * GET /api/combat/threat-pools/[?search=<term>]
 */
export async function fetchThreatPools(search?: string): Promise<ThreatPool[]> {
  const url = search
    ? `/api/combat/threat-pools/?search=${encodeURIComponent(search)}`
    : '/api/combat/threat-pools/';
  const res = await apiFetch(url);
  if (!res.ok) throw new Error('Failed to load threat pools');
  const data = (await res.json()) as { results?: ThreatPool[]; count?: number };
  return data.results ?? [];
}

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
// GM lifecycle (#3067) — encounter creation, NPC opponent spawn, manual round
// control. All gated server-side by IsEncounterGMOrStaff (CombatEncounterViewSet).
// ---------------------------------------------------------------------------

export type PaceMode = components['schemas']['PaceModeEnum'];
export type EncounterType = components['schemas']['EncounterTypeEnum'];
export type OpponentTier = components['schemas']['Tier756Enum'];
export type StakesLevel = components['schemas']['StakesLevelEnum'];
export type RiskLevel = components['schemas']['RiskLevelEnum'];

/**
 * Create a combat encounter for a scene (GM only) — the "Start encounter"
 * affordance (#3067). Only `scene` is required; the server defaults `room`
 * from the scene's current location (`CombatEncounterViewSet.perform_create`)
 * and `pace_mode`/`encounter_type`/etc. from their model defaults when
 * omitted.
 * POST /api/combat/
 */
export async function createEncounter(
  sceneId: number,
  options: { paceMode?: PaceMode; encounterType?: EncounterType } = {}
): Promise<EncounterDetail> {
  const res = await apiFetch('/api/combat/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      scene: sceneId,
      ...(options.paceMode !== undefined ? { pace_mode: options.paceMode } : {}),
      ...(options.encounterType !== undefined ? { encounter_type: options.encounterType } : {}),
    }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to start encounter');
  return res.json() as Promise<EncounterDetail>;
}

/** One row of the opponent-defaults scaling preview (GET .../opponent-defaults/). */
export interface OpponentDefaults {
  max_health: number;
  soak_value: number;
  probing_threshold: number | null;
  swarm_count: number | null;
  body_toughness: number | null;
  bodies_per_attack: number | null;
  barrier_strength: number | null;
  phases: { phase_number: number; health_trigger_percentage: number | null }[];
  stakes_ok: boolean;
  stakes_message: string;
}

/**
 * Preview the scaling formula's stat block for a tier, plus the stakes-gate
 * advisory (never blocks the preview itself — only a real add_opponent call).
 * GET /api/combat/{encounterId}/opponent-defaults/?tier=<tier>
 */
export async function fetchOpponentDefaults(
  encounterId: number,
  tier: OpponentTier
): Promise<OpponentDefaults> {
  const res = await apiFetch(
    `/api/combat/${encounterId}/opponent-defaults/?tier=${encodeURIComponent(tier)}`
  );
  if (!res.ok) await throwApiError(res, 'Failed to load opponent defaults');
  return res.json() as Promise<OpponentDefaults>;
}

/**
 * One row of the bestiary catalog (GET /api/combat/creature-templates/, #3424).
 * Deliberately thin — no phase/break-bar internals (see CreatureTemplateSerializer's
 * leak-table rationale); `has_phases` only signals presence.
 *
 * Typed locally rather than via the generated `components['schemas']` map — the
 * same pattern as `OpponentDefaults` above — so this file doesn't require an
 * `openapi-typescript` regen to compile.
 */
export interface CreatureTemplateSummary {
  id: number;
  name: string;
  tier: OpponentTier;
  description: string;
  has_phases: boolean;
  threat_pool_name: string | null;
}

/**
 * List authored CreatureTemplates (bestiary entries), optionally name/description
 * search-filtered and/or tier-filtered — the GM "spawn from bestiary" picker's
 * data source (#3424). GM/staff only server-side (`IsGMOrStaff`) — the bestiary
 * is spoiler-sensitive, unlike the open `ThreatPool` catalog.
 * GET /api/combat/creature-templates/[?search=<term>][&tier=<tier>]
 */
export async function fetchCreatureTemplates(
  search?: string,
  tier?: OpponentTier
): Promise<CreatureTemplateSummary[]> {
  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (tier) params.set('tier', tier);
  const query = params.toString();
  const url = query
    ? `/api/combat/creature-templates/?${query}`
    : '/api/combat/creature-templates/';
  const res = await apiFetch(url);
  if (!res.ok) throw new Error('Failed to load creature templates');
  const data = (await res.json()) as { results?: CreatureTemplateSummary[]; count?: number };
  return data.results ?? [];
}

/** Body for postAddOpponent — mirrors AddOpponentSerializer. */
export interface AddOpponentPayload {
  name: string;
  tier: OpponentTier;
  threatPoolId: number;
  maxHealth?: number | null;
  level?: number | null;
  description?: string;
  soakValue?: number;
  probingThreshold?: number | null;
  positionId?: number | null;
}

/**
 * Add an NPC opponent to the encounter (GM only). Omitting `maxHealth` selects
 * auto-scaling mode (the formula fills every stat field); `positionId` (#2005)
 * spawns the opponent already placed, must name a Position in the encounter's
 * own room.
 * POST /api/combat/{encounterId}/add_opponent/
 */
export async function postAddOpponent(
  encounterId: number,
  payload: AddOpponentPayload
): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/add_opponent/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: payload.name,
      tier: payload.tier,
      threat_pool_id: payload.threatPoolId,
      max_health: payload.maxHealth ?? undefined,
      level: payload.level ?? undefined,
      description: payload.description ?? '',
      soak_value: payload.soakValue ?? 0,
      probing_threshold: payload.probingThreshold ?? undefined,
      position_id: payload.positionId ?? undefined,
    }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to add opponent');
  return res.json() as Promise<EncounterDetail>;
}

/**
 * Add a PC to the encounter (GM only) — unlike `postJoin`, names any
 * character_sheet without an ownership requirement.
 * POST /api/combat/{encounterId}/add_participant/
 */
export async function postAddParticipant(
  encounterId: number,
  characterSheetId: number,
  covenantRoleId?: number | null
): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/add_participant/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      character_sheet_id: characterSheetId,
      ...(covenantRoleId != null ? { covenant_role_id: covenantRoleId } : {}),
    }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to add participant');
  return res.json() as Promise<EncounterDetail>;
}

/**
 * Remove a PC from the encounter (GM only).
 * POST /api/combat/{encounterId}/remove_participant/
 */
export async function postRemoveParticipant(
  encounterId: number,
  participantId: number
): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/remove_participant/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ participant_id: participantId }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to remove participant');
  return res.json() as Promise<EncounterDetail>;
}

/**
 * Remove an NPC opponent from the encounter (GM only, #3382).
 * POST /api/combat/{encounterId}/remove_opponent/
 */
export async function postRemoveOpponent(
  encounterId: number,
  opponentId: number
): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/remove_opponent/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ opponent_id: opponentId }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to remove opponent');
  return res.json() as Promise<EncounterDetail>;
}

/**
 * Begin a new declaration phase (GM only) — manual round control.
 * POST /api/combat/{encounterId}/begin_round/
 */
export async function postBeginRound(encounterId: number): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/begin_round/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) await throwApiError(res, 'Failed to begin round');
  return res.json() as Promise<EncounterDetail>;
}

/**
 * Resolve the current round (GM only) — manual round control.
 * POST /api/combat/{encounterId}/resolve_round/
 */
export async function postResolveRound(encounterId: number): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/resolve_round/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) await throwApiError(res, 'Failed to resolve round');
  return res.json() as Promise<EncounterDetail>;
}

/**
 * Toggle pause on the encounter timer (GM only).
 * POST /api/combat/{encounterId}/pause/
 */
export async function postPause(encounterId: number): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/pause/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) await throwApiError(res, 'Failed to toggle pause');
  return res.json() as Promise<EncounterDetail>;
}

// ---------------------------------------------------------------------------
// Encounter settings (GM only, #3383) — stakes/risk/pace/timer, changeable
// mid-encounter. Any subset of fields may be given; omitted fields are left
// unchanged server-side (update_encounter_settings).
// ---------------------------------------------------------------------------

export interface EncounterSettingsPayload {
  stakesLevel?: StakesLevel;
  riskLevel?: RiskLevel;
  paceMode?: PaceMode;
  paceTimerMinutes?: number;
}

/**
 * Change stakes/risk/pace/timer on a live encounter (GM only, #3383).
 * PATCH /api/combat/{encounterId}/settings/
 */
export async function patchEncounterSettings(
  encounterId: number,
  payload: EncounterSettingsPayload
): Promise<EncounterDetail> {
  const res = await apiFetch(`/api/combat/${encounterId}/settings/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...(payload.stakesLevel !== undefined ? { stakes_level: payload.stakesLevel } : {}),
      ...(payload.riskLevel !== undefined ? { risk_level: payload.riskLevel } : {}),
      ...(payload.paceMode !== undefined ? { pace_mode: payload.paceMode } : {}),
      ...(payload.paceTimerMinutes !== undefined
        ? { pace_timer_minutes: payload.paceTimerMinutes }
        : {}),
    }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to update encounter settings');
  return res.json() as Promise<EncounterDetail>;
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
// GM-initiated lethal duel proposal (#3068)
// ---------------------------------------------------------------------------

/** Opponent tier valid for a lethal duel — significant NPCs only. */
export type LethalDuelTier = components['schemas']['ProposeLethalDuelTierEnum'];

/** Body for postProposeLethalDuel — mirrors ProposeLethalDuelSerializer. */
export interface ProposeLethalDuelPayload {
  sceneId: number;
  challengedSheetId: number;
  opponentName: string;
  tier: LethalDuelTier;
  threatPoolId: number;
}

/**
 * GM proposes a lethal duel against a named PC (#3068). Creates a PENDING,
 * ``is_lethal`` DuelChallenge — no CombatEncounter exists until the targeted
 * PC accepts it via the normal duel-challenge inbox (accept/decline). GM
 * only, gated server-side by IsEncounterGMOrStaff (scene GM/owner or staff).
 * POST /api/combat/duel-challenges/propose_lethal_duel/
 */
export async function postProposeLethalDuel(
  payload: ProposeLethalDuelPayload
): Promise<DuelChallenge> {
  const res = await apiFetch('/api/combat/duel-challenges/propose_lethal_duel/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      scene: payload.sceneId,
      challenged_sheet_id: payload.challengedSheetId,
      opponent_name: payload.opponentName,
      tier: payload.tier,
      threat_pool_id: payload.threatPoolId,
    }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to propose the lethal duel');
  return res.json() as Promise<DuelChallenge>;
}

// ---------------------------------------------------------------------------
// Round combos (#3553)
// ---------------------------------------------------------------------------

/**
 * Fetch the combos taking shape this round, slot by slot.
 * GET /api/combat/{encounterId}/available_combos/
 */
export async function fetchAvailableCombos(encounterId: number): Promise<RoundCombo[]> {
  const res = await apiFetch(`/api/combat/${encounterId}/available_combos/`);
  if (!res.ok) throw new Error('Failed to load available combos');
  return res.json() as Promise<RoundCombo[]>;
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
