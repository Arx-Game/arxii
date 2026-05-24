/**
 * Combat React Query hooks.
 *
 * combatKeys factory mirrors the magicKeys pattern.
 * Phase 7 of the unified-combat-ui plan.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from './api';
import type { DispatchActionRequest } from './types';
import { fetchAvailableActions } from '@/scenes/actionQueries';
import type { PlayerAction } from '@/scenes/actionTypes';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const combatKeys = {
  all: ['combat'] as const,

  encounter: (encounterId: number) => [...combatKeys.all, 'encounter', encounterId] as const,

  combos: (encounterId: number) => [...combatKeys.all, 'combos', encounterId] as const,

  availableActions: (characterId: number) =>
    [...combatKeys.all, 'available-actions', characterId] as const,
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
      void qc.invalidateQueries({ queryKey: combatKeys.encounter(encounterId) });
      void qc.invalidateQueries({ queryKey: combatKeys.combos(encounterId) });
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
