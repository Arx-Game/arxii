/**
 * Magic React Query hooks
 *
 * Wraps api.ts functions with React Query hooks.
 * magicKeys factory provides consistent query keys for cache invalidation.
 *
 * Note: Soul Tether *formation* (acceptance) is handled by usePerformRitual
 * in the rituals module — not here.
 */

import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import * as api from './api';
import { performRitual } from '@/rituals/api';
import type { PerformRitualRequest } from '@/rituals/types';
import { useAppSelector } from '@/store/hooks';
import { combatKeys } from '@/combat/queries';
import { auraKeys } from './auraQueries';
import { availableActionsKeys } from '@/scenes/actionQueries';
import type {
  AcceptTeachingOfferRequest,
  AlterationResolvePayload,
  ApplicablePullsRequest,
  AudereRespondRequest,
  AudereMajoraRespondRequest,
  BindMotifStyleRequest,
  MotifFacetRequest,
  ChooseUltimateRequest,
  CrossXPLockRequest,
  DissolveRequest,
  SettlingRitePerformRequest,
  EntryFlourishRespondRequest,
  GlimpseDistinctionLinkRequest,
  PatchThreadRequest,
  PullPreviewRequest,
  RescueRequest,
  SineatingDeclineRequest,
  SetGlimpseProseRequest,
  SetGlimpseTagsRequest,
  StageAdvanceRespondRequest,
  TechniqueDesignRequest,
  TrainTechniqueRequest,
  UnbindMotifStyleRequest,
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

  stageAdvancePending: () => [...magicKeys.soulTether(), 'stage-advance', 'pending'] as const,
  stageAdvancePendingDetail: (id: number) => [...magicKeys.stageAdvancePending(), id] as const,

  tetherBonds: (sheetId: number) => [...magicKeys.soulTether(), 'bonds', sheetId] as const,

  threads: () => [...magicKeys.all, 'threads'] as const,
  threadList: () => [...magicKeys.threads(), 'list'] as const,
  thread: (id: number) => [...magicKeys.threads(), id] as const,
  threadResonanceOptions: (id: number, fromResonance?: number | null, amount?: number | null) =>
    [
      ...magicKeys.threads(),
      id,
      'resonance-options',
      fromResonance ?? null,
      amount ?? null,
    ] as const,

  // Scoped by sheet id (2026-07 audit): an unscoped key cached one alt's
  // balances/prospects and served them to every other character the account
  // viewed within staleTime. `null` = caller hasn't resolved a sheet yet.
  threadHubSummary: (characterSheetId?: number) =>
    [...magicKeys.all, 'thread-hub-summary', characterSheetId ?? null] as const,

  characterResonances: () => [...magicKeys.all, 'character-resonances'] as const,
  characterResonanceList: () => [...magicKeys.characterResonances(), 'list'] as const,

  characterGifts: (characterId: number) =>
    [...magicKeys.all, 'character-gifts', characterId] as const,

  teachingOffers: () => [...magicKeys.all, 'teaching-offers', 'list'] as const,

  technique: (id: number) => [...magicKeys.all, 'technique', id] as const,

  applicablePulls: (context: ApplicablePullsRequest | null) =>
    [...magicKeys.all, 'applicable-pulls', context] as const,

  pullBurnPreview: (request: PullPreviewRequest | null) =>
    [...magicKeys.all, 'pull-burn-preview', request] as const,

  characterAnima: (characterId: number) =>
    [...magicKeys.all, 'character-anima', characterId] as const,

  pendingAlterations: () => [...magicKeys.all, 'pending-alterations'] as const,
  alterationLibrary: (pendingId: number) =>
    [...magicKeys.pendingAlterations(), 'library', pendingId] as const,

  auderePending: () => [...magicKeys.all, 'audere', 'pending'] as const,
  manifestChoices: (characterSheetId: number) =>
    [...magicKeys.all, 'manifest-choices', characterSheetId] as const,

  resonanceCatalog: () => [...magicKeys.all, 'resonance-catalog'] as const,

  recordedActs: (characterSheetId: number) =>
    [...magicKeys.all, 'recorded-acts', characterSheetId] as const,

  kindledResonances: (characterSheetId: number) =>
    [...magicKeys.all, 'kindled-resonances', characterSheetId] as const,

  reflectionOptionsAll: () => [...magicKeys.all, 'reflection-options'] as const,
  reflectionOptions: (characterSheetId: number) =>
    [...magicKeys.all, 'reflection-options', characterSheetId] as const,

  sineatingOptions: (characterSheetId: number) =>
    [...magicKeys.all, 'sineating-options', characterSheetId] as const,

  audereUltimates: (characterSheetId: number) =>
    [...magicKeys.all, 'audere', 'ultimates', characterSheetId] as const,

  audereMajoraPending: () => [...magicKeys.all, 'audere-majora', 'pending'] as const,

  entryFlourishPending: () => [...magicKeys.all, 'entry-flourish', 'pending'] as const,

  driftConversionPending: () => [...magicKeys.all, 'drift-correction', 'pending'] as const,
  settlingRite: (characterSheetId: number) =>
    [...magicKeys.all, 'settling-rite', characterSheetId] as const,
  settlingRiteAll: () => [...magicKeys.all, 'settling-rite'] as const,

  pathIntent: (characterId: number) => [...magicKeys.all, 'path-intent', characterId] as const,

  pathOptions: (characterId: number) => [...magicKeys.all, 'path-options', characterId] as const,

  motifStyleBindings: (characterId: number) =>
    [...magicKeys.all, 'motif-styles', 'bindings', characterId] as const,
  styleCatalog: () => [...magicKeys.all, 'motif-styles', 'catalog'] as const,

  techniqueProgress: (characterId: number) =>
    [...magicKeys.all, 'technique-progress', characterId] as const,
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
 *
 * Pass ``{ enabled: false }`` to defer the fetch (e.g. until a cast dialog is
 * open). Defaults to ``true`` so all existing callers are unaffected.
 *
 * Pass ``characterSheetId`` to narrow to one owned character (#3898) — required
 * for any caller that shows one character at a time, so an account with alts does
 * not read another character's threads. Same narrowing, and the same reason, as
 * ``useCharacterResonances``. The id is part of the cache key, so the narrowed and
 * unnarrowed lists never share an entry.
 */
export function useThreads(options?: { enabled?: boolean; characterSheetId?: number }) {
  const characterSheetId = options?.characterSheetId;
  return useQuery({
    queryKey: [...magicKeys.threadList(), characterSheetId ?? 'all'],
    queryFn: () => api.getThreads(characterSheetId),
    throwOnError: true,
    enabled: options?.enabled ?? true,
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

/**
 * The gifts `characterId` holds (#4091) — backs the Bind-as-companion gift
 * picker on WonOverRows. Disabled when no character id is resolved yet, or
 * when the caller defers the fetch (e.g. until the form is open) via `enabled`.
 */
export function useCharacterGifts(characterId: number | null, enabled = true) {
  return useQuery({
    queryKey: magicKeys.characterGifts(characterId ?? 0),
    queryFn: () => api.fetchCharacterGifts(characterId as number),
    enabled: enabled && characterId !== null && characterId > 0,
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
      qc.invalidateQueries({
        queryKey: magicKeys.soulTetherDetail(variables.relationship_id),
      }).catch(() => {});
      qc.invalidateQueries({ queryKey: magicKeys.soulTether() }).catch(() => {});
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
      qc.invalidateQueries({ queryKey: magicKeys.soulTether() }).catch(() => {});
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
      qc.invalidateQueries({ queryKey: magicKeys.stageAdvancePending() }).catch(() => {});
      qc.invalidateQueries({ queryKey: magicKeys.soulTether() }).catch(() => {});
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
    queryKey: magicKeys.threadHubSummary(characterSheetId),
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
      qc.invalidateQueries({ queryKey: magicKeys.threadList() }).catch(() => {});
      qc.invalidateQueries({
        queryKey: [...magicKeys.all, 'thread-hub-summary'],
      }).catch(() => {});
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
      qc.invalidateQueries({ queryKey: magicKeys.thread(id) }).catch(() => {});
      qc.invalidateQueries({ queryKey: magicKeys.threadList() }).catch(() => {});
    },
  });
}

/** Resonance options for retuning a thread; fetched only while the dialog is open. */
export function useThreadResonanceOptions(
  threadId: number,
  enabled: boolean,
  move?: { fromResonance?: number | null; amount?: number | null }
) {
  return useQuery({
    queryKey: magicKeys.threadResonanceOptions(threadId, move?.fromResonance, move?.amount),
    queryFn: () => api.getThreadResonanceOptions(threadId, move),
    enabled,
    gcTime: 0,
  });
}

/**
 * Perform the retune rite (POST /api/magic/rituals/perform/) and refresh what it moves:
 * the threads, the hub summary and the resonance balances.
 */
export function useRetuneThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PerformRitualRequest) => performRitual(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: magicKeys.threads() }).catch(() => {});
      qc.invalidateQueries({
        queryKey: [...magicKeys.all, 'thread-hub-summary'],
      }).catch(() => {});
      qc.invalidateQueries({ queryKey: magicKeys.characterResonances() }).catch(() => {});
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
      qc.invalidateQueries({ queryKey: magicKeys.threadList() }).catch(() => {});
      qc.invalidateQueries({
        queryKey: [...magicKeys.all, 'thread-hub-summary'],
      }).catch(() => {});
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
      resonanceId,
    }: {
      characterSheetId: number;
      threadId: number;
      amount: number;
      /** The held resonance that pays (#5123); omitted, the thread's leading one pays. */
      resonanceId?: number | null;
    }) => api.imbueThreadAuto(characterSheetId, threadId, amount, resonanceId),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: magicKeys.thread(variables.threadId) }).catch(() => {});
      qc.invalidateQueries({
        queryKey: [...magicKeys.all, 'thread-hub-summary'],
      }).catch(() => {});
      qc.invalidateQueries({ queryKey: magicKeys.characterResonanceList() }).catch(() => {});
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
      qc.invalidateQueries({ queryKey: magicKeys.thread(variables.threadId) }).catch(() => {});
      qc.invalidateQueries({
        queryKey: [...magicKeys.all, 'thread-hub-summary'],
      }).catch(() => {});
      // Crossing an XP-lock spends account XP (2026-07 audit): without this the
      // ThreadDetailPage "Available: N XP" affordability stayed stale up to 5min.
      qc.invalidateQueries({ queryKey: ['account-progression'] }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Technique detail hook
// ---------------------------------------------------------------------------

/**
 * Fetch a single Technique by PK, including intensity, control, and anima_cost.
 *
 * The technique's authored stats; the cast card shows runtime ones from `cast_preview` (#4799).
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
      qc.invalidateQueries({ queryKey: magicKeys.teachingOffers() }).catch(() => {});
      qc.invalidateQueries({
        queryKey: [...magicKeys.all, 'thread-hub-summary'],
      }).catch(() => {});
      // Accepting a teaching offer pays XP (2026-07 audit) — refresh the balance.
      qc.invalidateQueries({ queryKey: ['account-progression'] }).catch(() => {});
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
 * Pull preview carrying the burn numbers (#4736). The request must name a
 * technique_id or the response's `burn` is null. Disabled while `request` is null.
 */
export function usePullBurnPreview(request: PullPreviewRequest | null) {
  return useQuery({
    queryKey: magicKeys.pullBurnPreview(request),
    queryFn: () => api.previewPull(request!),
    enabled: request !== null,
    staleTime: 5_000,
  });
}

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
 * Invalidates the CG technique list (the only technique-list query) on
 * success so the builder's downstream pickers refresh.
 */
export function useAuthorTechnique() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TechniqueDesignRequest) => api.authorTechnique(body),
    onSuccess: () => {
      // 2026-07 audit: the literal ['techniques'] key matched no query anywhere
      // (the CG technique list lives under character-creation's factory), and
      // the magicKeys.all blast refetched every magic query incl. 5s-poll
      // inboxes. Invalidate the real consumer instead.
      qc.invalidateQueries({ queryKey: ['character-creation', 'techniques'] }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Pending alterations (Mage Scars), #877
// ---------------------------------------------------------------------------

/**
 * Account-wide OPEN pending alterations.
 *
 * Backs the site-wide PendingAlterationBanner, so it is auth-guarded like
 * useRitualSessionInbox (rituals/queries.ts) to avoid 403s + error-boundary
 * blowups on the login page. Polls at 30 s: overburn happens in live scenes
 * outside REST flows, so the banner needs background freshness, but a 5 s
 * site-wide poll would be wasteful for a rare state change.
 */
export function usePendingAlterations() {
  const account = useAppSelector((s) => s.auth.account);
  const hasCharacters = (account?.available_characters?.length ?? 0) > 0;
  return useQuery({
    queryKey: magicKeys.pendingAlterations(),
    queryFn: () => api.getPendingAlterations(),
    enabled: !!account && hasCharacters,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
}

/** Tier-matched library entries for one pending. null = dialog closed. */
export function useAlterationLibrary(pendingId: number | null) {
  return useQuery({
    queryKey: magicKeys.alterationLibrary(pendingId ?? 0),
    queryFn: () => api.getAlterationLibrary(pendingId as number),
    enabled: pendingId != null,
  });
}

// ---------------------------------------------------------------------------
// Audere offers, #873
// ---------------------------------------------------------------------------

/**
 * Pending Audere offers for the account. Mounted only inside the combat page
 * (offers exist only mid-encounter), so the 5 s poll runs only where it matters.
 * throwOnError deliberately NOT set: this backs an overlay/banner that must
 * degrade to rendering nothing on fetch errors (same rationale as
 * usePendingAlterations).
 */
export function usePendingAudereOffers(enabled: boolean = true) {
  return useQuery({
    queryKey: magicKeys.auderePending(),
    queryFn: () => api.getPendingAudereOffers(),
    refetchInterval: 5_000,
    enabled,
  });
}

/**
 * Accept or decline a pending Audere offer. Accepting changes the anima
 * maximum and applies the Audere condition, so invalidate the encounter and
 * anima queries alongside the inbox.
 */
export function useRespondToAudere(characterId: number, encounterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AudereRespondRequest) => api.respondToAudere(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: magicKeys.auderePending() }).catch(() => {});
      qc.invalidateQueries({ queryKey: magicKeys.characterAnima(characterId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: combatKeys.encounter(encounterId) }).catch(() => {});
    },
  });
}

/**
 * The in-progress Audere ultimate reveal/readied state + deferred-death banner
 * for the given character (#4098). Owner-only; polled only while a ceremony
 * runs (`enabled` is gated by the caller, e.g. `isAudereActive || isMajoraActive`).
 * throwOnError deliberately NOT set: backs an overlay, same rationale as
 * usePendingAudereOffers.
 */
export function useAudereUltimates(characterSheetId: number, enabled: boolean) {
  return useQuery({
    queryKey: magicKeys.audereUltimates(characterSheetId),
    queryFn: () => api.getAudereUltimates(characterSheetId),
    refetchInterval: 5_000,
    enabled: enabled && characterSheetId > 0,
  });
}

/**
 * Choose (reveal or re-cast) an ultimate by its choice_key. On success the
 * readied ultimate now appears among the combat actions, so invalidate both
 * the Audere ultimates state and the player's available actions, plus the
 * encounter itself (mirrors useRespondToAudere's post-respond refresh).
 */
export function useChooseUltimate(
  characterSheetId: number,
  characterId: number,
  encounterId: number
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ChooseUltimateRequest) => api.chooseUltimate(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: magicKeys.audereUltimates(characterSheetId) }).catch(
        () => {}
      );
      qc.invalidateQueries({ queryKey: availableActionsKeys.forCharacter(characterId) }).catch(
        () => {}
      );
      qc.invalidateQueries({ queryKey: combatKeys.encounter(encounterId) }).catch(() => {});
    },
  });
}

/** Resolve a pending via either path; refreshes the banner/page list on success. */
export function useResolveAlteration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      pendingId,
      payload,
    }: {
      pendingId: number;
      payload: AlterationResolvePayload;
    }) => api.resolveAlteration(pendingId, payload),
    onSuccess: () => {
      // Prefix-invalidates alterationLibrary(id) queries too — intended: a
      // resolved pending's library snapshot is dead weight.
      qc.invalidateQueries({ queryKey: magicKeys.pendingAlterations() }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Audere Majora (Crossing offer), #543
// ---------------------------------------------------------------------------

/**
 * Pending Audere Majora crossing offers for the account. Mounted only inside
 * the combat panel; the 5 s poll runs only where it matters.
 * throwOnError deliberately NOT set: same rationale as usePendingAudereOffers.
 */
export function usePendingAudereMajoraOffers(enabled: boolean = true) {
  return useQuery({
    queryKey: magicKeys.audereMajoraPending(),
    queryFn: () => api.getPendingAudereMajoraOffers(),
    refetchInterval: 5_000,
    enabled,
  });
}

/**
 * Accept or decline a pending Audere Majora crossing offer.
 * On success invalidates the majora inbox, the base audere inbox (both poll
 * the combat panel), and the path intent (a crossing may clear or confirm it).
 */
export function useRespondToAudereMajora(characterId: number, encounterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AudereMajoraRespondRequest) => api.respondToAudereMajora(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: magicKeys.audereMajoraPending() }).catch(() => {});
      qc.invalidateQueries({ queryKey: magicKeys.auderePending() }).catch(() => {});
      // Prefix-invalidate all pathIntent keys (any characterId).
      qc.invalidateQueries({ queryKey: [...magicKeys.all, 'path-intent'] }).catch(() => {});
      // A crossing changes level, conditions, and combat state — mirror
      // useRespondToAudere's post-respond refreshes.
      qc.invalidateQueries({ queryKey: magicKeys.characterAnima(characterId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: combatKeys.encounter(encounterId) }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Entry-flourish offers, #1140
// ---------------------------------------------------------------------------

/**
 * Pending entry-flourish offers for the account. Mounted only inside the scene
 * entry flow (offers exist only at scene-entry moments), so the 5 s poll runs
 * only where it matters.
 * throwOnError deliberately NOT set: same rationale as usePendingAudereOffers —
 * this backs an overlay/banner that must degrade to rendering nothing on fetch errors.
 */
export function usePendingEntryFlourishOffers(enabled: boolean = true) {
  return useQuery({
    queryKey: magicKeys.entryFlourishPending(),
    queryFn: () => api.getPendingEntryFlourishOffers(),
    refetchInterval: 5_000,
    enabled,
  });
}

/**
 * Pick a resonance to broadcast for a pending entry-flourish offer.
 *
 * Takes the responding character's sheet id (consumed by callers; kept for
 * call-site compatibility). The respond endpoint runs grant_resonance, which
 * changes CharacterResonance balance/lifetime_earned.
 *
 * On success invalidates:
 * - the entry-flourish pending inbox (offer clears)
 * - magicKeys.characterResonanceList() — the key used by useCharacterResonances
 *   (covers all per-sheet entries via prefix match)
 */
export function useRespondToEntryFlourish(_characterSheetId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EntryFlourishRespondRequest) => api.respondToEntryFlourish(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: magicKeys.entryFlourishPending() }).catch(() => {});
      qc.invalidateQueries({ queryKey: magicKeys.characterResonanceList() }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// The open chance to atone (#4733) and the rite of settling (#5124)
// ---------------------------------------------------------------------------

/**
 * The account's open chances to atone: one per character, open until the rite spends it, so
 * it is read when the sheet is, not polled. throwOnError deliberately NOT set: same
 * rationale as usePendingEntryFlourishOffers.
 */
export function usePendingDriftConversionOffers(enabled: boolean = true) {
  return useQuery({
    queryKey: magicKeys.driftConversionPending(),
    queryFn: () => api.getPendingDriftConversionOffers(),
    enabled,
  });
}

/**
 * A deed was earned: what a reflection can name now includes it, and the rite's reading changes
 * with it. The same two keys `usePerformSettlingRite` invalidates, from the live "You earned ..."
 * line (the server tags that text frame `earned_resonance`) so the "Reflecting on" row lists the
 * deed without a reload.
 */
export function refreshReflectableDeeds(queryClient: QueryClient): void {
  queryClient.invalidateQueries({ queryKey: magicKeys.reflectionOptionsAll() }).catch(() => {});
  queryClient.invalidateQueries({ queryKey: magicKeys.settlingRiteAll() }).catch(() => {});
}

/**
 * What the rite of settling would take for one character: their waiting reflections, the
 * carried items that count as the offering, and whether the rite is set up. Owner only, so
 * a viewer of someone else's sheet passes `enabled` false.
 */
export function useSettlingRite(characterSheetId: number, enabled: boolean = true) {
  return useQuery({
    queryKey: magicKeys.settlingRite(characterSheetId),
    queryFn: () => api.getSettlingRite(characterSheetId),
    enabled,
  });
}

/**
 * Perform the rite of settling.
 *
 * On success invalidates the reading (every reflection took the rite), the pending chance to
 * atone (a cap shrinks or the chance closes), what can be reflected on, the resonances (a
 * deed grew or a conversion moved them), the auras and the character sheets (the character
 * may now be settled, so the sheet must not keep reading her as unsettled).
 */
export function usePerformSettlingRite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SettlingRitePerformRequest) => api.performSettlingRite(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: magicKeys.settlingRiteAll() }).catch(() => {});
      qc.invalidateQueries({ queryKey: magicKeys.driftConversionPending() }).catch(() => {});
      qc.invalidateQueries({ queryKey: magicKeys.reflectionOptionsAll() }).catch(() => {});
      qc.invalidateQueries({ queryKey: magicKeys.characterResonanceList() }).catch(() => {});
      qc.invalidateQueries({ queryKey: auraKeys.all }).catch(() => {});
      qc.invalidateQueries({ queryKey: ['character-sheets'] }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// PathIntent, #543
// ---------------------------------------------------------------------------

/**
 * Current path intent for the given character.
 * Returns `{ intent: null }` when none is declared.
 * Disabled when characterId ≤ 0.
 */
export function usePathIntent(characterId: number) {
  return useQuery({
    queryKey: magicKeys.pathIntent(characterId),
    queryFn: () => api.getPathIntent(characterId),
    enabled: characterId > 0,
  });
}

/** Declare (or overwrite) the calling character's path intent. */
export function useDeclarePathIntent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ characterId, pathId }: { characterId: number; pathId: number }) =>
      api.putPathIntent(characterId, pathId),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: magicKeys.pathIntent(variables.characterId) }).catch(
        () => {}
      );
    },
  });
}

/** Clear the calling character's path intent. */
export function useClearPathIntent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (characterId: number) => api.deletePathIntent(characterId),
    onSuccess: (_data, characterId) => {
      qc.invalidateQueries({ queryKey: magicKeys.pathIntent(characterId) }).catch(() => {});
    },
  });
}

/** Current path + selectable next paths for the character. Disabled when id ≤ 0. */
export function useNextPathOptions(characterId: number) {
  return useQuery({
    queryKey: magicKeys.pathOptions(characterId),
    queryFn: () => api.getNextPathOptions(characterId),
    enabled: characterId > 0,
  });
}

// ---------------------------------------------------------------------------
// Motif style bindings, #2030
// ---------------------------------------------------------------------------

/** The current Motif style bindings for the given (viewed) character. */
export function useMotifStyleBindings(characterId: number) {
  return useQuery({
    queryKey: magicKeys.motifStyleBindings(characterId),
    queryFn: () => api.getMotifStyleBindings(characterId),
    enabled: characterId > 0,
  });
}

/** The player-facing Style catalog, for the bind form's style picker. */
export function useStyleCatalog() {
  return useQuery({
    queryKey: magicKeys.styleCatalog(),
    queryFn: () => api.getStyleCatalog(),
  });
}

/**
 * Bind a Style to one of the given character's claimed resonances
 * (`characterSheetId` backs the `X-Character-ID` header, scoping the mutation
 * to that character rather than the caller's active puppet).
 *
 * On success invalidates the bindings list and the character sheet query
 * (`['character-sheets', characterSheetId]`, per character_sheets/queries.ts'
 * useCharacterSheetQuery) — the sheet's magic.motif.resonances[*].styles
 * mirrors the same bindings.
 */
export function useBindMotifStyle(characterSheetId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BindMotifStyleRequest) => api.bindMotifStyle(characterSheetId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: magicKeys.motifStyleBindings(characterSheetId) }).catch(
        () => {}
      );
      qc.invalidateQueries({ queryKey: ['character-sheets', characterSheetId] }).catch(() => {});
    },
  });
}

/**
 * Tie (`tie: true`) or untie a facet on one of the character's claimed resonances
 * (#5021). Same character scoping and invalidation as useBindMotifStyle: the sheet's
 * magic.motif.resonances[*].facets mirrors these ties.
 */
export function useSetMotifFacet(characterSheetId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ tie, ...body }: MotifFacetRequest & { tie: boolean }) =>
      api.setMotifFacet(characterSheetId, body, tie),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: magicKeys.motifStyleBindings(characterSheetId) }).catch(
        () => {}
      );
      qc.invalidateQueries({ queryKey: ['character-sheets', characterSheetId] }).catch(() => {});
    },
  });
}

/** Remove a Style binding. Same character scoping + invalidation as useBindMotifStyle. */
export function useUnbindMotifStyle(characterSheetId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: UnbindMotifStyleRequest) => api.unbindMotifStyle(characterSheetId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: magicKeys.motifStyleBindings(characterSheetId) }).catch(
        () => {}
      );
      qc.invalidateQueries({ queryKey: ['character-sheets', characterSheetId] }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Glimpse aura actions, #2427 — the "finish later" character-sheet editor.
//
// Every hook here is keyed by `auraId` (the endpoint's own path param, from
// `CharacterSheetAura.id`) but takes `characterSheetId` too so it can
// invalidate the character-sheet query on success — the same
// `['character-sheets', characterSheetId]` key `useCharacterSheetQuery`
// (character_sheets/queries.ts) reads, which is where `glimpse_state` /
// `glimpse_tags` / `glimpse_story` actually live. The aura action responses
// themselves are not consumed (see the "Glimpse aura actions" note in api.ts).
// ---------------------------------------------------------------------------

function invalidateGlimpseSheet(qc: ReturnType<typeof useQueryClient>, characterSheetId: number) {
  qc.invalidateQueries({ queryKey: ['character-sheets', characterSheetId] }).catch(() => {});
}

/** Replace one axis's glimpse tag picks. */
export function useSetGlimpseTags(auraId: number, characterSheetId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SetGlimpseTagsRequest) => api.setGlimpseTags(auraId, body),
    onSuccess: () => invalidateGlimpseSheet(qc, characterSheetId),
  });
}

/** Write the glimpse story prose. */
export function useSetGlimpseProse(auraId: number, characterSheetId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SetGlimpseProseRequest) => api.setGlimpseProse(auraId, body),
    onSuccess: () => invalidateGlimpseSheet(qc, characterSheetId),
  });
}

/**
 * Link/unlink a CharacterDistinction to the glimpse. Wraps both endpoints
 * behind one `toggle(characterDistinctionId, isCurrentlyLinked)` call so
 * callers (GlimpseEditorDialog) don't need to pick the mutation themselves.
 */
export function useToggleGlimpseDistinction(auraId: number, characterSheetId: number) {
  const qc = useQueryClient();
  const link = useMutation({
    mutationFn: (body: GlimpseDistinctionLinkRequest) => api.linkGlimpseDistinction(auraId, body),
    onSuccess: () => invalidateGlimpseSheet(qc, characterSheetId),
  });
  const unlink = useMutation({
    mutationFn: (body: GlimpseDistinctionLinkRequest) => api.unlinkGlimpseDistinction(auraId, body),
    onSuccess: () => invalidateGlimpseSheet(qc, characterSheetId),
  });
  return {
    toggle: (characterDistinctionId: number, isCurrentlyLinked: boolean) => {
      const mutation = isCurrentlyLinked ? unlink : link;
      mutation.mutate({ character_distinction_id: characterDistinctionId });
    },
    isPending: link.isPending || unlink.isPending,
  };
}

// ---------------------------------------------------------------------------
// Technique progress meters, #2739
// ---------------------------------------------------------------------------

/** The given character's in-progress technique training meters. Disabled when id ≤ 0. */
export function useTechniqueProgress(characterId: number) {
  return useQuery({
    queryKey: magicKeys.techniqueProgress(characterId),
    queryFn: () => api.getTechniqueProgress(characterId),
    enabled: characterId > 0,
  });
}

/**
 * Run one training session against a technique's meter for the given
 * character (`characterSheetId` backs the `X-Character-ID` header, same
 * scoping convention as `useBindMotifStyle`).
 *
 * On success invalidates the meter list so the refetched progress/teacher/
 * weekly-remaining figures reflect the session immediately, plus the
 * character-sheet query (`['character-sheets', characterSheetId]`, per
 * `character_sheets/queries.ts`' `useCharacterSheetQuery` — same pattern as
 * `useBindMotifStyle`/`useUnbindMotifStyle` above) — a completed session can
 * mint a `CharacterTechnique`, which `SpellbookTab` renders from that sheet
 * payload, not from this meter list. Unconditional (not gated on
 * `technique_acquired`) to match that precedent.
 */
export function useTrainTechnique(characterSheetId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ techniqueId, body }: { techniqueId: number; body?: TrainTechniqueRequest }) =>
      api.trainTechnique(characterSheetId, techniqueId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: magicKeys.techniqueProgress(characterSheetId) }).catch(
        () => {}
      );
      qc.invalidateQueries({ queryKey: ['character-sheets', characterSheetId] }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Technique picker (#4341)
// ---------------------------------------------------------------------------

/** What each manifesting technique the character knows can bring into a fight. */
export function useManifestChoices(characterSheetId: number) {
  return useQuery({
    queryKey: magicKeys.manifestChoices(characterSheetId),
    queryFn: () => api.getManifestChoices(characterSheetId),
    enabled: characterSheetId > 0,
  });
}

/**
 * Choose what a technique brings (`manifest_set`). A refusal comes back as
 * `success === false` with the reason, so it is thrown for the panel to show.
 */
export function useSetManifestChoice(characterSheetId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ techniqueId, optionId }: { techniqueId: number; optionId: number }) => {
      const result = await api.setManifestChoice(characterSheetId, techniqueId, optionId);
      if (result.success === false) throw new Error(result.message);
      return result;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: magicKeys.manifestChoices(characterSheetId) }).catch(
        () => {}
      );
      qc.invalidateQueries({ queryKey: ['character-sheets', characterSheetId] }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Your resonances (#5124)
// ---------------------------------------------------------------------------

/** Every resonance in the game, in her aura or not (#5308): a pose reaches for, and a flourish declares, any of them. */
export function useResonanceCatalog() {
  return useQuery({
    queryKey: magicKeys.resonanceCatalog(),
    queryFn: api.getResonanceCatalog,
    staleTime: 300_000,
  });
}

/** How often the panel re-reads what is kindled; it changes as a scene or a fight moves. */
const KINDLED_RESONANCES_REFETCH_MS = 30_000;

/** Every character's kindled-resonances reading, re-read (a deed was earned). */
export function refreshKindledResonances(queryClient: QueryClient): void {
  queryClient
    .invalidateQueries({ queryKey: [...magicKeys.all, 'kindled-resonances'] })
    .catch(() => {});
}

/**
 * The acts the character has not marked and can still point at (#5327), newest first. Empty
 * until the reading loads, and while `characterSheetId` is unknown.
 */
export function useRecordedActs(characterSheetId: number | null, enabled = true) {
  return useQuery({
    queryKey: magicKeys.recordedActs(characterSheetId ?? 0),
    queryFn: () => api.getRecordedActs(characterSheetId ?? 0),
    enabled: enabled && characterSheetId != null && characterSheetId > 0,
  });
}

/** Re-read what a character can point at, once a mark has used an act up. */
export function useRefreshRecordedActs(characterSheetId: number | null) {
  const queryClient = useQueryClient();
  return () => {
    if (characterSheetId == null) return;
    void queryClient.invalidateQueries({ queryKey: magicKeys.recordedActs(characterSheetId) });
  };
}

/**
 * What the character can reflect on now (#5124): the resonance unsettling them, then each
 * kindled deed not yet reflected on. Empty when there is nothing, and until `characterSheetId`
 * is known.
 */
export function useReflectionOptions(characterSheetId: number | null) {
  return useQuery({
    queryKey: magicKeys.reflectionOptions(characterSheetId ?? 0),
    queryFn: () => api.getReflectionOptions(characterSheetId ?? 0),
    enabled: characterSheetId != null && characterSheetId > 0,
  });
}

/** Re-read what a character can reflect on, once a reflection is recorded. */
export function useRefreshReflectionOptions(characterSheetId: number | null) {
  const queryClient = useQueryClient();
  return () => {
    if (characterSheetId == null) return;
    void queryClient.invalidateQueries({
      queryKey: magicKeys.reflectionOptions(characterSheetId),
    });
  };
}

/**
 * What a pose can carry as a Sineating (#5177): a plea to make to each Sineater here, and a
 * plea to answer for each one waiting. Polled, so a plea made in the scene shows up on the
 * Sineater's composer without a reload. Empty until `characterSheetId` is known, and off while
 * `enabled` is false (no active scene).
 */
export function useSineatingOptions(characterSheetId: number | null, enabled = true) {
  return useQuery({
    queryKey: magicKeys.sineatingOptions(characterSheetId ?? 0),
    queryFn: () => api.getSineatingOptions(characterSheetId ?? 0),
    enabled: enabled && characterSheetId != null && characterSheetId > 0,
    refetchInterval: 5_000,
  });
}

/**
 * Re-read what a Sineating changes once a pose carrying one posts: the options themselves,
 * the Soul Tether (Hollow and the Mire carried), and what a reflection can name (a Sineater
 * now carries a Mire to reflect on).
 */
export function useRefreshSineating(characterSheetId: number | null) {
  const queryClient = useQueryClient();
  return () => {
    if (characterSheetId != null) {
      void queryClient.invalidateQueries({
        queryKey: magicKeys.sineatingOptions(characterSheetId),
      });
    }
    void queryClient.invalidateQueries({ queryKey: magicKeys.soulTether() });
    void queryClient.invalidateQueries({ queryKey: magicKeys.reflectionOptionsAll() });
  };
}

/** A Sineater turns a waiting plea down; the options re-read so it leaves the row. */
export function useDeclineSineating() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SineatingDeclineRequest) => api.declineSineating(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...magicKeys.all, 'sineating-options'] });
    },
  });
}

/**
 * Each resonance the character holds, kindled or not, with the strength word and reasons, and
 * the impulses their carried corruption stirs.
 */
export function useKindledResonances(characterSheetId: number) {
  return useQuery({
    queryKey: magicKeys.kindledResonances(characterSheetId),
    queryFn: () => api.getKindledResonances(characterSheetId),
    enabled: characterSheetId > 0,
    refetchInterval: KINDLED_RESONANCES_REFETCH_MS,
  });
}
