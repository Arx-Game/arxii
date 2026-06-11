/**
 * Combat React Query hooks.
 *
 * combatKeys factory mirrors the magicKeys pattern.
 * Phase 7 of the unified-combat-ui plan.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from './api';
import type { DispatchActionRequest, EncounterListItem } from './types';
import { fetchAvailableActions } from '@/scenes/actionQueries';
import type { PlayerAction } from '@/scenes/actionTypes';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const combatKeys = {
  all: ['combat'] as const,

  encounter: (encounterId: number) => [...combatKeys.all, 'encounter', encounterId] as const,

  encountersForScene: (sceneId: number) =>
    [...combatKeys.all, 'encounters-for-scene', sceneId] as const,

  combos: (encounterId: number) => [...combatKeys.all, 'combos', encounterId] as const,

  availableActions: (characterId: number) =>
    [...combatKeys.all, 'available-actions', characterId] as const,

  outcomeDetails: (ids: number[]) => [...combatKeys.all, 'outcome-details', ids] as const,

  consequenceOutcomes: (params: api.ConsequenceOutcomesParams) =>
    [...combatKeys.all, 'consequence-outcomes', params] as const,
};

// ---------------------------------------------------------------------------
// Encounter read hook
// ---------------------------------------------------------------------------

/**
 * Fetch the full encounter state.
 * Polls every 10 seconds to stay current during the declaration phase.
 * Disabled when encounterId <= 0.
 */
export function useCombatEncounter(encounterId: number) {
  return useQuery({
    queryKey: combatKeys.encounter(encounterId),
    queryFn: () => api.fetchEncounter(encounterId),
    enabled: encounterId > 0,
    refetchInterval: 10_000,
    staleTime: 5_000,
  });
}

// ---------------------------------------------------------------------------
// Encounter-for-scene hook
// ---------------------------------------------------------------------------

/**
 * Return the most-recent active (non-completed) encounter for a scene.
 *
 * Queries GET /api/combat/?scene=<sceneId> and returns the first encounter
 * whose status is not "completed". Returns null when none exists.
 *
 * The most recent non-completed encounter is the canonical active one for the
 * scene. Multiple in-flight encounters per scene is unsupported but not
 * constraint-enforced in the backend. The API returns results ordered
 * -created_at (see CombatEncounterViewSet.get_queryset), so the first
 * non-completed entry is always deterministic regardless of how many exist.
 *
 * Polls every 15 seconds so the page stays current during encounter creation.
 * Disabled when sceneId <= 0.
 */
export function useEncounterForScene(sceneId: number): {
  data: EncounterListItem | null | undefined;
  isLoading: boolean;
  isError: boolean;
} {
  const result = useQuery({
    queryKey: combatKeys.encountersForScene(sceneId),
    queryFn: () => api.fetchEncountersForScene(sceneId),
    enabled: sceneId > 0,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });

  // Filter to non-completed encounters. The API guarantees -created_at ordering,
  // so taking index 0 is deterministic: it is always the most-recent non-completed
  // encounter. Using .find() was equally correct here but index 0 makes the
  // intent explicit.
  const nonCompleted = result.data?.filter((e: EncounterListItem) => e.status !== 'completed');
  const activeEncounter = nonCompleted && nonCompleted.length > 0 ? nonCompleted[0] : null;

  return {
    data: result.isLoading ? undefined : activeEncounter,
    isLoading: result.isLoading,
    isError: result.isError,
  };
}

// ---------------------------------------------------------------------------
// Available combos hook
// ---------------------------------------------------------------------------

/**
 * Fetch combo upgrade options for the encounter.
 * Disabled when encounterId <= 0.
 */
export function useAvailableCombos(encounterId: number) {
  return useQuery({
    queryKey: combatKeys.combos(encounterId),
    queryFn: () => api.fetchAvailableCombos(encounterId),
    enabled: encounterId > 0,
    staleTime: 5_000,
  });
}

// ---------------------------------------------------------------------------
// Upgrade combo mutation hook
// ---------------------------------------------------------------------------

/**
 * Upgrade the current action to a combo.
 * Invalidates the encounter and combos keys on success.
 */
export function useUpgradeCombo(encounterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (comboId: number) => api.postUpgradeCombo(encounterId, comboId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: combatKeys.encounter(encounterId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: combatKeys.combos(encounterId) }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Available actions hook (combat-scoped)
//
// Fetches all PlayerActions for the character and filters to COMBAT backend.
// Clash-contribution actions appear here too with ref.clash_id !== null.
// ---------------------------------------------------------------------------

/**
 * Fetch COMBAT-backend PlayerActions for the character.
 *
 * Wraps GET /api/actions/characters/{characterId}/available/ and filters
 * results where ref.backend === 'COMBAT'. Clash contribution actions appear
 * here too with ref.clash_id !== null.
 *
 * Disabled when characterId <= 0.
 */
export function useAvailableActions(characterId: number): {
  data: PlayerAction[];
  isLoading: boolean;
  isError: boolean;
} {
  const result = useQuery({
    queryKey: combatKeys.availableActions(characterId),
    queryFn: () => fetchAvailableActions(characterId),
    enabled: characterId > 0,
    staleTime: 10_000,
  });

  const combatActions = (result.data?.results ?? []).filter(
    (a: PlayerAction) => a.ref.backend === 'COMBAT'
  );

  return {
    data: combatActions,
    isLoading: result.isLoading,
    isError: result.isError,
  };
}

// ---------------------------------------------------------------------------
// Dispatch player action mutation hook
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Outcome details hook (lazy fetch for PoseUnitDetailPanel)
// ---------------------------------------------------------------------------

/**
 * Fetch outcome details for a set of ACTION Interactions.
 * Disabled when no IDs are provided.
 */
export function useOutcomeDetails(actionInteractionIds: number[]) {
  return useQuery({
    queryKey: combatKeys.outcomeDetails(actionInteractionIds),
    queryFn: () => api.fetchOutcomeDetails(actionInteractionIds),
    enabled: actionInteractionIds.length > 0,
    staleTime: 30_000,
  });
}

// ---------------------------------------------------------------------------
// Dispatch player action mutation hook
// ---------------------------------------------------------------------------

/**
 * Dispatch a player action — unified write path for focused, passive, and
 * clash-contribution actions.
 *
 * POST /api/actions/characters/{characterId}/dispatch/
 * Body: { ref: ActionRef, kwargs: Record<string, unknown> }
 *
 * Does not auto-invalidate — the caller (YourTurn submit handler) controls
 * when to refetch the encounter.
 */
export function useDispatchPlayerAction(characterId: number) {
  return useMutation({
    mutationFn: (body: DispatchActionRequest) => api.postDispatchAction(characterId, body),
  });
}

// ---------------------------------------------------------------------------
// Flee mutation hook
// ---------------------------------------------------------------------------

/**
 * Declare flee for the current round.
 * POST /api/combat/{encounterId}/flee/
 * Invalidates encounter key on success.
 */
export function useFleeMutation(encounterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.postFlee(encounterId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: combatKeys.encounter(encounterId) }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Cover mutation hook
// ---------------------------------------------------------------------------

/**
 * Declare cover for an ally participant.
 * POST /api/combat/{encounterId}/cover/
 * Invalidates encounter key on success.
 */
export function useCoverMutation(encounterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (allyParticipantId: number) => api.postCover(encounterId, allyParticipantId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: combatKeys.encounter(encounterId) }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Consequence outcomes hook
// ---------------------------------------------------------------------------

/**
 * Fetch ConsequenceOutcome records for a character (or pool).
 *
 * Returns the roulette display + modifier breakdown for each outcome.
 * Disabled when no params are provided (avoids a fetch-all).
 * staleTime is generous — outcomes are append-only, never mutated.
 */
export function useConsequenceOutcomes(params: api.ConsequenceOutcomesParams) {
  // Only enable when a meaningful filter is provided (> 0 to guard against un-initialized ids).
  const hasFilter =
    (params.character !== undefined && params.character > 0) ||
    (params.pool !== undefined && params.pool > 0);
  return useQuery({
    queryKey: combatKeys.consequenceOutcomes(params),
    queryFn: () => api.fetchConsequenceOutcomes(params),
    enabled: hasFilter,
    staleTime: 60_000,
  });
}
