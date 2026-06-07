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
  AcceptTeachingOfferRequest,
  ApplicablePullsRequest,
  CrossXPLockRequest,
  DissolveRequest,
  PatchThreadRequest,
  PullCommitRequest,
  RescueRequest,
  SineatingRequest,
  SineatingRespondRequest,
  StageAdvanceRespondRequest,
  TechniqueDesignRequest,
  WeaveThreadRequest,
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

  tetherBonds: (sheetId: number) => [...magicKeys.soulTether(), 'bonds', sheetId] as const,

  threads: () => [...magicKeys.all, 'threads'] as const,
  threadList: () => [...magicKeys.threads(), 'list'] as const,
  thread: (id: number) => [...magicKeys.threads(), id] as const,

  threadHubSummary: () => [...magicKeys.all, 'thread-hub-summary'] as const,

  characterResonances: () => [...magicKeys.all, 'character-resonances'] as const,
  characterResonanceList: () => [...magicKeys.characterResonances(), 'list'] as const,

  teachingOffers: () => [...magicKeys.all, 'teaching-offers', 'list'] as const,

  technique: (id: number) => [...magicKeys.all, 'technique', id] as const,

  applicablePulls: (context: ApplicablePullsRequest | null) =>
    [...magicKeys.all, 'applicable-pulls', context] as const,

  characterAnima: (characterId: number) =>
    [...magicKeys.all, 'character-anima', characterId] as const,
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
 * Enumerate the calling character's soul-tether bonds.
 *
 * Issues two queries — source and target — and merges results so that bonds
 * where the caller is on either side of the relationship are included.
 *
 * Returns an array of TetherBond objects with the bonded character's sheet id,
 * name, and soul_tether_role. When myCharacterSheetId is null the hook is
 * disabled and returns an empty array.
 */
export function useMyTetherBonds(myCharacterSheetId: number | null) {
  return useQuery({
    queryKey: magicKeys.tetherBonds(myCharacterSheetId ?? 0),
    queryFn: () => api.getMyTetherBonds(myCharacterSheetId!),
    enabled: myCharacterSheetId !== null && myCharacterSheetId > 0,
    throwOnError: true,
  });
}

/**
 * Sineater inbox: paginated list of pending Sineating offers.
 * Polls every 5 seconds for new offers so the Sineater sees them without refreshing.
 */
export function usePendingSineatingOffers() {
  return useQuery({
    queryKey: magicKeys.sineatingPending(),
    queryFn: () => api.getPendingSineatingOffers(),
    refetchInterval: 5_000,
    throwOnError: true,
  });
}

/**
 * Sineater inbox: paginated list of pending stage-advance bonus offers.
 * Polls every 5 seconds for new offers so the Sineater sees them without refreshing.
 */
export function usePendingStageAdvanceOffers() {
  return useQuery({
    queryKey: magicKeys.stageAdvancePending(),
    queryFn: () => api.getPendingStageAdvanceOffers(),
    refetchInterval: 5_000,
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
 * Fetch CharacterResonance rows scoped to the requesting account.
 *
 * Pass ``characterSheetId`` to narrow the result to a single character —
 * required for any caller that operates on one character at a time, so
 * users with alts don't see resonances from other characters mixed in.
 *
 * Currently also used inline by ResonancePickerField in the rituals module
 * (see rituals/components/fields/ResonancePickerField.tsx TODO). A follow-up
 * task will import this hook there instead of the inline duplicate.
 */
export function useCharacterResonances(characterSheetId?: number) {
  return useQuery({
    queryKey: [...magicKeys.characterResonanceList(), characterSheetId ?? null],
    queryFn: () => api.getCharacterResonances(characterSheetId),
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

// ---------------------------------------------------------------------------
// Thread Hub Summary hook
// ---------------------------------------------------------------------------

/**
 * Fetch the Thread Hub summary for the acting character.
 * Pass characterSheetId for alt-guard disambiguation.
 */
export function useThreadHubSummary(characterSheetId?: number) {
  return useQuery({
    queryKey: magicKeys.threadHubSummary(),
    queryFn: () => api.getThreadHubSummary(characterSheetId),
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Thread detail hook
// ---------------------------------------------------------------------------

/**
 * Fetch a single Thread by PK.
 * Disabled when id ≤ 0.
 */
export function useThread(id: number) {
  return useQuery({
    queryKey: magicKeys.thread(id),
    queryFn: () => api.getThread(id),
    enabled: id > 0,
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Teaching Offers read hook
// ---------------------------------------------------------------------------

/**
 * Fetch all ThreadWeavingTeachingOffer records visible to the caller.
 */
export function useTeachingOffers() {
  return useQuery({
    queryKey: magicKeys.teachingOffers(),
    queryFn: () => api.getTeachingOffers(),
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Thread mutation hooks
// ---------------------------------------------------------------------------

/**
 * Weave a new Thread.
 * Invalidates threadList and threadHubSummary on success.
 */
export function useWeaveThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WeaveThreadRequest) => api.weaveThread(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: magicKeys.threadList() });
      void qc.invalidateQueries({ queryKey: magicKeys.threadHubSummary() });
    },
  });
}

/**
 * Patch a Thread's narrative fields (name, description).
 * Invalidates the thread detail and threadList on success.
 */
export function usePatchThreadNarrative(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PatchThreadRequest) => api.patchThreadNarrative(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: magicKeys.thread(id) });
      void qc.invalidateQueries({ queryKey: magicKeys.threadList() });
    },
  });
}

/**
 * Soft-retire a Thread.
 * Invalidates threadList and threadHubSummary on success.
 */
export function useRetireThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (threadId: number) => api.retireThread(threadId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: magicKeys.threadList() });
      void qc.invalidateQueries({ queryKey: magicKeys.threadHubSummary() });
    },
  });
}

/**
 * Imbue a thread (spend resonance to advance it).
 *
 * Accepts { characterSheetId, threadId, amount } and delegates to
 * api.imbueThreadAuto which resolves the ritual id internally.
 *
 * Invalidates thread(id), threadHubSummary, and characterResonanceList.
 */
export function useImbueThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      characterSheetId,
      threadId,
      amount,
    }: {
      characterSheetId: number;
      threadId: number;
      amount: number;
    }) => api.imbueThreadAuto(characterSheetId, threadId, amount),
    onSuccess: (_data, variables) => {
      void qc.invalidateQueries({ queryKey: magicKeys.thread(variables.threadId) });
      void qc.invalidateQueries({ queryKey: magicKeys.threadHubSummary() });
      void qc.invalidateQueries({ queryKey: magicKeys.characterResonanceList() });
    },
  });
}

/**
 * Cross an XP-lock boundary on a Thread.
 * Invalidates thread(id) and threadHubSummary on success.
 */
export function useCrossXPLock() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ threadId, body }: { threadId: number; body: CrossXPLockRequest }) =>
      api.crossXPLock(threadId, body),
    onSuccess: (_data, variables) => {
      void qc.invalidateQueries({ queryKey: magicKeys.thread(variables.threadId) });
      void qc.invalidateQueries({ queryKey: magicKeys.threadHubSummary() });
    },
  });
}

/**
 * Commit a thread pull: spends resonance and applies effects.
 * Invalidates threadHubSummary and characterResonanceList on success.
 *
 * Note: previewPull is a plain async helper (api.previewPull), not a hook,
 * because previews are user-driven and ephemeral. Components should debounce
 * calls to api.previewPull manually.
 */
export function useCommitPull() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PullCommitRequest) => api.commitPull(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: magicKeys.threadHubSummary() });
      void qc.invalidateQueries({ queryKey: magicKeys.characterResonanceList() });
    },
  });
}

// ---------------------------------------------------------------------------
// Technique detail hook
// ---------------------------------------------------------------------------

/**
 * Fetch a single Technique by PK, including intensity, control, and anima_cost.
 *
 * Used by ActionDeclarationCard to render the I/C chip and cost preview.
 * Disabled when id is undefined or 0.
 */
export function useTechnique(id: number | undefined) {
  return useQuery({
    queryKey: magicKeys.technique(id ?? 0),
    queryFn: () => api.getTechnique(id!),
    enabled: id !== undefined && id > 0,
    staleTime: 60_000,
  });
}

/**
 * Accept a ThreadWeavingTeachingOffer.
 * Invalidates teachingOffers and threadHubSummary on success.
 */
export function useAcceptTeachingOffer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ offerId, body }: { offerId: number; body?: AcceptTeachingOfferRequest }) =>
      api.acceptTeachingOffer(offerId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: magicKeys.teachingOffers() });
      void qc.invalidateQueries({ queryKey: magicKeys.threadHubSummary() });
    },
  });
}

// ---------------------------------------------------------------------------
// Applicable Pulls read hook
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Character Anima read hook
// ---------------------------------------------------------------------------

/**
 * Fetch the CharacterAnima record for the given character (ObjectDB PK).
 *
 * Disabled when characterId <= 0.
 * The CharacterAnima ViewSet filters by ?character=<pk> (ObjectDB PK, not
 * CharacterSheet PK). Each character has at most one CharacterAnima row.
 */
export function useCharacterAnima(characterId: number) {
  return useQuery({
    queryKey: magicKeys.characterAnima(characterId),
    queryFn: () => api.getCharacterAnima(characterId),
    enabled: characterId > 0,
    staleTime: 10_000,
  });
}

// ---------------------------------------------------------------------------
// Applicable Pulls read hook
// ---------------------------------------------------------------------------

/**
 * Fetch per-thread applicability rows for the given action context.
 *
 * Disabled when context is null (no action context available yet).
 * staleTime: 5_000 — context changes are user-driven and quick;
 * short stale time keeps the picker reactive.
 */
export function useApplicablePulls(context: ApplicablePullsRequest | null) {
  return useQuery({
    queryKey: magicKeys.applicablePulls(context),
    queryFn: () => api.fetchApplicablePulls(context!),
    enabled: context !== null,
    staleTime: 5_000,
  });
}

// ---------------------------------------------------------------------------
// Technique builder mutation hooks
// ---------------------------------------------------------------------------

/**
 * Dry-run pricing mutation for the technique builder live budget meter.
 *
 * Returns TechniqueCostBreakdown (tier, budget, total_cost, within_budget, lines).
 * Not wired to cache invalidation — pricing is ephemeral and read-only.
 * The form component should debounce calls rather than firing on every keystroke.
 */
export function usePriceTechnique() {
  return useMutation({
    mutationFn: (body: TechniqueDesignRequest) => api.priceTechnique(body),
  });
}

/**
 * Author a technique via the budget policy layer.
 *
 * Invalidates the technique list on success so any downstream technique
 * lists refresh. magicKeys does not have a techniqueList key, so we use
 * a literal ['techniques'] queryKey to match any technique list query.
 */
export function useAuthorTechnique() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TechniqueDesignRequest) => api.authorTechnique(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['techniques'] });
      void qc.invalidateQueries({ queryKey: magicKeys.all });
    },
  });
}
