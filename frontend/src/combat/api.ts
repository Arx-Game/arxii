/**
 * Combat API client functions.
 *
 * Plain async functions — not hooks. React Query hooks live in queries.ts.
 * Phase 7 of the unified-combat-ui plan.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type {
  AvailableCombo,
  DispatchActionRequest,
  DispatchResult,
  EncounterDetail,
  EncounterListItem,
} from './types';

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
export async function fetchEncountersForScene(
  sceneId: number
): Promise<EncounterListItem[]> {
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
