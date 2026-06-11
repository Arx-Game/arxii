/**
 * Combat API client functions.
 *
 * Plain async functions — not hooks. React Query hooks live in queries.ts.
 * Phase 7 of the unified-combat-ui plan.
 */

import { apiFetch } from '@/evennia_replacements/api';
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

/**
 * A single row in the outcome_display roulette wheel.
 * The backend serializes OutcomeDisplay dataclass as plain dicts.
 */
export interface OutcomeDisplayRow {
  label: string;
  tier_name: string;
  weight: number;
  is_selected: boolean;
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
  if (!res.ok) {
    let detail = 'Failed to declare flee';
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
  if (!res.ok) {
    let detail = 'Failed to declare cover';
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
  deep_link: { modal: string; id: number } | null;
}

export interface ActionOutcomeDetail {
  action_interaction_id: number;
  effects: OutcomeEffectRow[];
  power_ledger?: PowerLedger | null;
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
  if (!res.ok) {
    let detail = 'Failed to dispatch action';
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
  return res.json() as Promise<DispatchResult>;
}
