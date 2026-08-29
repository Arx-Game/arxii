/**
 * Combat React Query hooks.
 *
 * combatKeys factory mirrors the magicKeys pattern.
 * Phase 7 of the unified-combat-ui plan.
 */

import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import * as api from './api';
import type {
  DispatchActionRequest,
  DispatchResult,
  EncounterDetail,
  EncounterListItem,
} from './types';
import { availableActionsKeys, useAvailableActionsQuery } from '@/scenes/actionQueries';
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

  outcomeDetails: (ids: number[]) => [...combatKeys.all, 'outcome-details', ids] as const,

  consequenceOutcomes: (params: api.ConsequenceOutcomesParams) =>
    [...combatKeys.all, 'consequence-outcomes', params] as const,

  duelChallengesAll: () => [...combatKeys.all, 'duel-challenges'] as const,

  duelChallenges: (role?: api.DuelChallengeRole) =>
    [...combatKeys.duelChallengesAll(), role ?? 'all'] as const,

  threatPools: (search?: string) => [...combatKeys.all, 'threat-pools', search ?? ''] as const,

  opponentDefaults: (encounterId: number, tier: api.OpponentTier) =>
    [...combatKeys.all, 'opponent-defaults', encounterId, tier] as const,

  creatureTemplates: (search?: string, tier?: api.OpponentTier) =>
    [...combatKeys.all, 'creature-templates', search ?? '', tier ?? ''] as const,
};

/**
 * Invalidate every consequence-outcome query (all character/encounter variants),
 * so the "Last Outcome" panel refetches after a round-affecting mutation (#866).
 */
export function invalidateConsequenceOutcomes(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: [...combatKeys.all, 'consequence-outcomes'] }).catch(() => {});
}

/**
 * Mutation hook for a simple combat action whose only cache effect is to refresh
 * the encounter detail and the consequence-outcome panel. Hooks with extra
 * invalidations (useEndEncounter, useUpgradeCombo) stay bespoke.
 */
function useEncounterMutation<TData, TArgs = void>(
  encounterId: number,
  mutationFn: (args: TArgs) => Promise<TData>
) {
  const qc = useQueryClient();
  return useMutation<TData, Error, TArgs>({
    mutationFn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: combatKeys.encounter(encounterId) }).catch(() => {});
      invalidateConsequenceOutcomes(qc);
    },
  });
}

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
// Duel-challenge inbox hook
// ---------------------------------------------------------------------------

/**
 * Fetch the requesting player's PENDING duel challenges (#1180).
 *
 * GET /api/combat/duel-challenges/[?role=...]. The result is scoped server-side
 * to the caller's played characters, so the page filters by challenged.id to find
 * the incoming challenge for the active character. Polls so an incoming challenge
 * appears without a manual refresh; disabled via `enabled` (e.g. when no character
 * is resolved).
 */
export function useDuelChallengeInbox(
  options: { enabled?: boolean; role?: api.DuelChallengeRole } = {}
) {
  const { enabled = true, role } = options;
  return useQuery({
    queryKey: combatKeys.duelChallenges(role),
    queryFn: () => api.fetchDuelChallengeInbox(role),
    enabled,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}

/**
 * GM proposes a lethal duel against a named PC (#3068). Invalidates the
 * duel-challenge inbox key so the targeted player's poll (DuelChallengeNotifier)
 * picks up the new PENDING challenge without waiting for its own 15s cycle.
 */
export function useProposeLethalDuel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: api.ProposeLethalDuelPayload) => api.postProposeLethalDuel(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: combatKeys.duelChallengesAll() }).catch(() => {});
    },
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
      qc.invalidateQueries({ queryKey: combatKeys.encounter(encounterId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: combatKeys.combos(encounterId) }).catch(() => {});
      invalidateConsequenceOutcomes(qc);
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
 * COMBAT-backend PlayerActions for the character. Thin filter over the shared
 * useAvailableActionsQuery; polls at 10s to match useCombatEncounter's
 * declaration-phase contract (#2423 finding 6) so round advances and clash
 * spawns reach the technique list within one poll period.
 */
export function useAvailableActions(characterId: number): {
  data: PlayerAction[];
  isLoading: boolean;
  isError: boolean;
} {
  const result = useAvailableActionsQuery(characterId, { refetchInterval: 10_000 });
  const combatActions = (result.data?.results ?? []).filter(
    (a: PlayerAction) => a.ref.backend === 'combat'
  );
  return { data: combatActions, isLoading: result.isLoading, isError: result.isError };
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
  return useEncounterMutation(encounterId, () => api.postFlee(encounterId));
}

// ---------------------------------------------------------------------------
// Join / Leave mutation hooks (Open Encounters)
// ---------------------------------------------------------------------------

/**
 * Player self-joins an Open Encounter.
 * POST /api/combat/{encounterId}/join/
 * Arg: characterSheetId (number). Invalidates encounter key on success.
 */
export function useJoinMutation(encounterId: number) {
  return useEncounterMutation(encounterId, (characterSheetId: number) =>
    api.postJoin(encounterId, characterSheetId)
  );
}

/**
 * Player voluntarily leaves an Open Encounter between rounds.
 * POST /api/combat/{encounterId}/leave/
 * Invalidates encounter key on success.
 */
export function useLeaveMutation(encounterId: number) {
  return useEncounterMutation(encounterId, () => api.postLeave(encounterId));
}

// ---------------------------------------------------------------------------
// End encounter mutation hook (GM only)
// ---------------------------------------------------------------------------

/**
 * End the encounter early (GM only), recording the "abandoned" outcome (#876).
 * POST /api/combat/{encounterId}/end/
 *
 * Invalidates the encounter detail key and the scene's encounter list on
 * success — the list feeds useEncounterForScene's active-encounter selection,
 * which must stop returning this encounter once it completes.
 */
export function useEndEncounter(encounterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.postEndEncounter(encounterId),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: combatKeys.encounter(encounterId) }).catch(() => {});
      // Terminal event: every character's action list for this fight is now stale.
      qc.invalidateQueries({ queryKey: availableActionsKeys.all }).catch(() => {});
      invalidateConsequenceOutcomes(qc);
      if (typeof data.scene === 'number') {
        qc.invalidateQueries({ queryKey: combatKeys.encountersForScene(data.scene) }).catch(
          () => {}
        );
      }
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
  return useEncounterMutation(encounterId, (allyParticipantId: number) =>
    api.postCover(encounterId, allyParticipantId)
  );
}

// ---------------------------------------------------------------------------
// Guard (Interpose) mutation hook
// ---------------------------------------------------------------------------

/**
 * Args for useGuardMutation — ward + optional protective technique (#2207) +
 * optional redirect destination (#2210, mutually exclusive; both null = "away").
 */
export interface GuardMutationArgs {
  allyParticipantId: number | null;
  techniqueId: number | null;
  redirectOpponentTargetId?: number | null;
  redirectObjectTargetId?: number | null;
}

/**
 * Declare a guarding (Interpose) maneuver, optionally naming a ward ally
 * and/or a protective technique (#2207 — "Guard" in the UI, `interpose` on the
 * wire/maneuver enum), and — when the technique is REDIRECT-flavored — an
 * optional saved-damage destination (#2210). Unlike flee/cover, Interpose has
 * no dedicated REST verb that accepts `technique_id` — `InterposeSerializer`
 * (world/combat/serializers.py) only carries `ally_participant_id` — so this
 * rides the generic REGISTRY dispatch path (`combat_interpose`) via
 * `api.postDispatchAction` instead of a bespoke `api.post*` wrapper, the same
 * seam `MovementActions`/the focused-slot dispatch already use. Reuses
 * `useEncounterMutation` so the cache-invalidation contract matches flee/cover.
 */
export function useGuardMutation(encounterId: number, characterId: number) {
  return useEncounterMutation<DispatchResult, GuardMutationArgs>(
    encounterId,
    ({ allyParticipantId, techniqueId, redirectOpponentTargetId, redirectObjectTargetId }) =>
      api.postDispatchAction(characterId, {
        ref: { backend: 'registry', registry_key: 'combat_interpose' },
        kwargs: {
          ally_participant_id: allyParticipantId,
          technique_id: techniqueId,
          redirect_opponent_target_id: redirectOpponentTargetId ?? null,
          redirect_object_target_id: redirectObjectTargetId ?? null,
        },
      })
  );
}

// ---------------------------------------------------------------------------
// Generic registry-maneuver dispatch hook (#3381)
// ---------------------------------------------------------------------------

/** Args for useRegistryDispatch — a bare registry_key + kwargs, no bespoke shape. */
export interface RegistryDispatchArgs {
  registryKey: string;
  kwargs?: Record<string, unknown>;
}

/**
 * Dispatch a registry-backend maneuver that has no dedicated REST wrapper and
 * needs no bespoke request shape — rally/succor/taunt/demoralize/parley/
 * combat_revert/combat_charge/combat_joust (#3381 Decision 1: all new wiring
 * rides the generic dispatch seam). Generalizes `useGuardMutation`'s shape
 * (POST via `api.postDispatchAction`, invalidate the encounter + consequence-
 * outcome caches on success via `useEncounterMutation`) over an arbitrary
 * registry_key/kwargs pair, since none of these verbs need Guard's bespoke
 * redirect-destination handling. Callers still check `isDispatchFailure(result)`
 * themselves — a business-rule rejection resolves HTTP 200 with `success: false`
 * (#2423), and invalidating on that is harmless (the refetch returns unchanged
 * state).
 */
export function useRegistryDispatch(encounterId: number, characterId: number) {
  return useEncounterMutation<DispatchResult, RegistryDispatchArgs>(
    encounterId,
    ({ registryKey, kwargs = {} }) =>
      api.postDispatchAction(characterId, {
        ref: { backend: 'registry', registry_key: registryKey },
        kwargs,
      })
  );
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
    (params.pool !== undefined && params.pool > 0) ||
    (params.encounter !== undefined && params.encounter > 0);
  return useQuery({
    queryKey: combatKeys.consequenceOutcomes(params),
    queryFn: () => api.fetchConsequenceOutcomes(params),
    enabled: hasFilter,
    staleTime: 5_000,
  });
}

// ---------------------------------------------------------------------------
// GM lifecycle hooks (#3067) — encounter creation, NPC opponent spawn,
// manual round control. All gated server-side by IsEncounterGMOrStaff.
// ---------------------------------------------------------------------------

/**
 * List the ThreatPool catalog for the add-opponent picker, optionally
 * name-filtered. Not encounter-scoped — authored content, long staleTime.
 */
export function useThreatPools(search?: string) {
  return useQuery({
    queryKey: combatKeys.threatPools(search),
    queryFn: () => api.fetchThreatPools(search),
    staleTime: 60_000,
  });
}

/**
 * Preview the scaling formula's stat block + stakes-gate advisory for a tier.
 * Disabled until a tier is chosen.
 */
export function useOpponentDefaults(encounterId: number, tier: api.OpponentTier | null) {
  return useQuery({
    queryKey: combatKeys.opponentDefaults(encounterId, tier ?? 'mook'),
    queryFn: () => api.fetchOpponentDefaults(encounterId, tier as api.OpponentTier),
    enabled: encounterId > 0 && tier !== null,
  });
}

/**
 * Create an encounter for a scene (GM only) — the "Start encounter"
 * affordance. Invalidates the scene's encounter-list key on success so
 * useEncounterForScene picks up the new encounter without a manual refetch.
 */
export function useCreateEncounter(sceneId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (options: { paceMode?: api.PaceMode; encounterType?: api.EncounterType } = {}) =>
      api.createEncounter(sceneId, options),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: combatKeys.encountersForScene(sceneId) }).catch(() => {});
    },
  });
}

/** Add an NPC opponent to the encounter (GM only). */
export function useAddOpponent(encounterId: number) {
  return useEncounterMutation<EncounterDetail, api.AddOpponentPayload>(encounterId, (payload) =>
    api.postAddOpponent(encounterId, payload)
  );
}

/**
 * List the CreatureTemplate bestiary catalog for the "From bestiary" spawn
 * picker (#3424), optionally name/description search-filtered and/or
 * tier-filtered. Not encounter-scoped — authored content, long staleTime
 * (mirrors `useThreatPools`).
 */
export function useCreatureTemplates(search?: string, tier?: api.OpponentTier) {
  return useQuery({
    queryKey: combatKeys.creatureTemplates(search, tier),
    queryFn: () => api.fetchCreatureTemplates(search, tier),
    staleTime: 60_000,
  });
}

/**
 * Spawn an authored CreatureTemplate bestiary entry into the encounter
 * (GM only, #3424). Unlike `useAddOpponent` (a bespoke `add_opponent` REST
 * verb on `CombatEncounterViewSet`), `spawn_creature` carries no dedicated
 * REST action — it rides the generic REGISTRY dispatch seam
 * (`api.postDispatchAction`), the same pattern `useGuardMutation` established
 * for `combat_interpose`. Reuses `useEncounterMutation` so the cache-
 * invalidation contract matches every other GM lifecycle mutation here.
 */
export function useSpawnCreature(encounterId: number, characterId: number) {
  return useEncounterMutation<DispatchResult, { template: string; positionId: number | null }>(
    encounterId,
    ({ template, positionId }) =>
      api.postDispatchAction(characterId, {
        ref: { backend: 'registry', registry_key: 'spawn_creature' },
        kwargs: { template, position_id: positionId },
      })
  );
}

/** Add a PC to the encounter (GM only) — names any character_sheet, no ownership check. */
export function useAddParticipant(encounterId: number) {
  return useEncounterMutation<
    EncounterDetail,
    { characterSheetId: number; covenantRoleId?: number | null }
  >(encounterId, ({ characterSheetId, covenantRoleId }) =>
    api.postAddParticipant(encounterId, characterSheetId, covenantRoleId)
  );
}

/** Remove a PC from the encounter (GM only). */
export function useRemoveParticipant(encounterId: number) {
  return useEncounterMutation<EncounterDetail, number>(encounterId, (participantId) =>
    api.postRemoveParticipant(encounterId, participantId)
  );
}

/** Remove an NPC opponent from the encounter (GM only, #3382). */
export function useRemoveOpponent(encounterId: number) {
  return useEncounterMutation<EncounterDetail, number>(encounterId, (opponentId) =>
    api.postRemoveOpponent(encounterId, opponentId)
  );
}

/** Begin a new declaration phase (GM only) — manual round control. */
export function useBeginRound(encounterId: number) {
  return useEncounterMutation<EncounterDetail, void>(encounterId, () =>
    api.postBeginRound(encounterId)
  );
}

/** Resolve the current round (GM only) — manual round control. */
export function useResolveRound(encounterId: number) {
  return useEncounterMutation<EncounterDetail, void>(encounterId, () =>
    api.postResolveRound(encounterId)
  );
}

/** Change stakes/risk/pace/timer on a live encounter (GM only, #3383). */
export function useUpdateEncounterSettings(encounterId: number) {
  return useEncounterMutation<EncounterDetail, api.EncounterSettingsPayload>(
    encounterId,
    (payload) => api.patchEncounterSettings(encounterId, payload)
  );
}

/** Toggle pause on the encounter timer (GM only). */
export function usePauseEncounter(encounterId: number) {
  return useEncounterMutation<EncounterDetail, void>(encounterId, () => api.postPause(encounterId));
}
