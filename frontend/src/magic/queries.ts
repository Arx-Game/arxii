/**
 * Magic React Query hooks
 *
 * Wraps api.ts functions with React Query hooks.
 * magicKeys factory provides consistent query keys for cache invalidation.
 *
 * Note: Soul Tether *formation* (acceptance) is handled by usePerformRitual
 * in the rituals module — not here.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from './api';
import type {
  DissolveRequest,
  RescueRequest,
  SineatingRequest,
  SineatingRespondRequest,
  StageAdvanceRespondRequest,
} from './types';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const magicKeys = {
  all: ['magic'] as const,

  soulTether: () => [...magicKeys.all, 'soul-tether'] as const,
  soulTetherDetail: (relationshipId: number) =>
    [...magicKeys.soulTether(), 'detail', relationshipId] as const,

  sineatingPending: () => [...magicKeys.soulTether(), 'sineating', 'pending'] as const,
  sineatingPendingDetail: (id: number) => [...magicKeys.sineatingPending(), id] as const,

  stageAdvancePending: () => [...magicKeys.soulTether(), 'stage-advance', 'pending'] as const,
  stageAdvancePendingDetail: (id: number) => [...magicKeys.stageAdvancePending(), id] as const,

  threads: () => [...magicKeys.all, 'threads'] as const,
  threadList: () => [...magicKeys.threads(), 'list'] as const,

  characterResonances: () => [...magicKeys.all, 'character-resonances'] as const,
  characterResonanceList: () => [...magicKeys.characterResonances(), 'list'] as const,
};

// ---------------------------------------------------------------------------
// Soul Tether read hooks
// ---------------------------------------------------------------------------

/**
 * Fetch the tether state for a given CharacterRelationship PK.
 * Either directional row PK is accepted by the backend.
 */
export function useSoulTetherDetail(relationshipId: number) {
  return useQuery({
    queryKey: magicKeys.soulTetherDetail(relationshipId),
    queryFn: () => api.getSoulTetherDetail(relationshipId),
    enabled: relationshipId > 0,
    throwOnError: true,
  });
}

/**
 * Sineater inbox: paginated list of pending Sineating offers.
 */
export function usePendingSineatingOffers() {
  return useQuery({
    queryKey: magicKeys.sineatingPending(),
    queryFn: () => api.getPendingSineatingOffers(),
    throwOnError: true,
  });
}

/**
 * Sineater inbox: paginated list of pending stage-advance bonus offers.
 */
export function usePendingStageAdvanceOffers() {
  return useQuery({
    queryKey: magicKeys.stageAdvancePending(),
    queryFn: () => api.getPendingStageAdvanceOffers(),
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Thread read hooks
// ---------------------------------------------------------------------------

/**
 * Fetch the caller's threads (account-scoped, excluding retired).
 */
export function useThreads() {
  return useQuery({
    queryKey: magicKeys.threadList(),
    queryFn: () => api.getThreads(),
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// CharacterResonance read hooks
// ---------------------------------------------------------------------------

/**
 * Fetch all CharacterResonance rows for the requesting account's characters.
 *
 * Currently also used inline by ResonancePickerField in the rituals module
 * (see rituals/components/fields/ResonancePickerField.tsx TODO). A follow-up
 * task will import this hook there instead of the inline duplicate.
 */
export function useCharacterResonances() {
  return useQuery({
    queryKey: magicKeys.characterResonanceList(),
    queryFn: () => api.getCharacterResonances(),
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Soul Tether mutation hooks
// ---------------------------------------------------------------------------

/**
 * Dissolve a Soul Tether bond.
 *
 * Invalidates the tether detail for the dissolved relationship and the broad
 * soul-tether key so any downstream data refreshes.
 */
export function useDissolveSoulTether() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: DissolveRequest) => api.dissolveSoulTether(body),
    onSuccess: (_data, variables) => {
      void qc.invalidateQueries({
        queryKey: magicKeys.soulTetherDetail(variables.relationship_id),
      });
      void qc.invalidateQueries({ queryKey: magicKeys.soulTether() });
    },
  });
}

/**
 * Sinner initiates a Sineating request.
 *
 * Returns the SineatingOffer payload. Invalidates the pending sineating list
 * so the Sineater's inbox refreshes.
 */
export function useRequestSineating() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SineatingRequest) => api.requestSineating(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: magicKeys.sineatingPending() });
    },
  });
}

/**
 * Sineater accepts or declines a pending Sineating offer.
 *
 * units_accepted=0 is a decline. Invalidates the pending list and the
 * soul-tether detail so Hollow state updates.
 */
export function useRespondToSineating() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SineatingRespondRequest) => api.respondToSineating(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: magicKeys.sineatingPending() });
      void qc.invalidateQueries({ queryKey: magicKeys.soulTether() });
    },
  });
}

/**
 * Sineater performs the rescue ritual on the Sinner (stage 3+ only).
 *
 * Invalidates the soul-tether detail so stage and strain data refresh.
 */
export function usePerformRescue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RescueRequest) => api.performRescue(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: magicKeys.soulTether() });
    },
  });
}

/**
 * Sineater responds to a stage-advance bonus offer.
 *
 * units_committed=0 is a decline. Invalidates the pending list and the
 * soul-tether detail.
 */
export function useRespondToStageAdvance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: StageAdvanceRespondRequest) => api.respondToStageAdvance(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: magicKeys.stageAdvancePending() });
      void qc.invalidateQueries({ queryKey: magicKeys.soulTether() });
    },
  });
}
