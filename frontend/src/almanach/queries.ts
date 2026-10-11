/**
 * Almanach de Catenys React Query layer (#3983 Task 7), mirroring
 * `world-builder/queries.ts`: a hierarchical `almanachKeys` factory plus one
 * query hook per read and a single mutation hook every staff verb dispatches
 * through.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { useWorldBuilderActor } from '@/world-builder/useWorldBuilderActor';

import {
  dispatchAlmanach,
  fetchCharter,
  fetchFamilyDocument,
  fetchFamilyKinds,
  fetchFront,
  fetchGenders,
  fetchHoldingKinds,
  fetchHouseDocument,
  fetchHouses,
  fetchLadder,
  fetchLandShapes,
  fetchPersonDocument,
  fetchRealms,
  fetchSearch,
  fetchTemplates,
  fetchTitleDocument,
  fetchUnionKinds,
  fetchRealmTitles,
  fetchVacantTitles,
} from './api';
import type { AlmanachActionKey, LadderMode } from './types';

/** Hierarchical key namespace with matchable prefixes (project convention,
 * mirrors `worldBuilderKeys`). */
export const almanachKeys = {
  all: ['almanach'] as const,
  realms: () => [...almanachKeys.all, 'realms'] as const,
  ladder: (realmId: number, mode: LadderMode) =>
    [...almanachKeys.all, 'ladder', realmId, mode] as const,
  houses: (realmId: number) => [...almanachKeys.all, 'houses', realmId] as const,
  allHouses: () => [...almanachKeys.all, 'houses', 'all'] as const,
  document: (houseId: number) => [...almanachKeys.all, 'document', houseId] as const,
  landShapes: () => [...almanachKeys.all, 'land-shapes'] as const,
  genders: () => [...almanachKeys.all, 'genders'] as const,
  charter: (realmId: number) => [...almanachKeys.all, 'charter', realmId] as const,
  // #4239
  front: (q: string) => [...almanachKeys.all, 'front', q] as const,
  search: (q: string) => [...almanachKeys.all, 'search', q] as const,
  person: (personId: number) => [...almanachKeys.all, 'person', personId] as const,
  title: (titleId: number) => [...almanachKeys.all, 'title', titleId] as const,
  family: (familyId: number) => [...almanachKeys.all, 'family', familyId] as const,
  kinds: () => [...almanachKeys.all, 'kinds'] as const,
  templates: (realmId: number, kindId: number | null) =>
    [...almanachKeys.all, 'templates', realmId, kindId] as const,
  unionKinds: (realmId: number | null) => [...almanachKeys.all, 'union-kinds', realmId] as const,
  vacantTitles: (realmId: number) => [...almanachKeys.all, 'vacant-titles', realmId] as const,
  realmTitles: (realmId: number) => [...almanachKeys.all, 'realm-titles', realmId] as const,
  holdingKinds: () => [...almanachKeys.all, 'holding-kinds'] as const,
};

export function useRealms() {
  return useQuery({
    queryKey: almanachKeys.realms(),
    queryFn: fetchRealms,
    staleTime: 30_000,
  });
}

export function useLadder(realmId: number | null | undefined, mode: LadderMode) {
  return useQuery({
    queryKey: almanachKeys.ladder(realmId ?? 0, mode),
    queryFn: () => fetchLadder(realmId!, mode),
    enabled: realmId != null,
    staleTime: 15_000,
  });
}

/** The realm's houses (#3983 Task 8's "a house on record" select). Disabled
 * (no fetch) when `realmId` is null/undefined — `PlantRungDialog` relies on
 * that to skip the request until its "held by a house" toggle is on. */
export function useHouses(realmId: number | null | undefined) {
  return useQuery({
    queryKey: almanachKeys.houses(realmId ?? 0),
    queryFn: () => fetchHouses(realmId!),
    enabled: realmId != null,
    staleTime: 30_000,
  });
}

/**
 * Every house in the game, unscoped (#3983 Task 9): the House Document route
 * carries no realm id (the document's `realm` section reports title/demesne
 * facts, never a realm identity), so resolving a vassal's held-by name to a
 * house link, and populating the "swear a house"/"born into" pickers, have
 * nothing to scope a realm-filtered fetch to. Always enabled, unlike
 * `useHouses` — there's no "not ready yet" state here, only "fetch everyone."
 */
export function useAllHouses() {
  return useQuery({
    queryKey: almanachKeys.allHouses(),
    queryFn: () => fetchHouses(),
    staleTime: 30_000,
  });
}

/** The site-wide gender catalog (#3983 Task 9's kin editor). */
export function useGenders() {
  return useQuery({
    queryKey: almanachKeys.genders(),
    queryFn: fetchGenders,
    staleTime: 300_000,
  });
}

export function useHouseDocument(houseId: number | null | undefined) {
  return useQuery({
    queryKey: almanachKeys.document(houseId ?? 0),
    queryFn: () => fetchHouseDocument(houseId!),
    enabled: houseId != null,
    staleTime: 15_000,
  });
}

export function useLandShapes() {
  return useQuery({
    queryKey: almanachKeys.landShapes(),
    queryFn: fetchLandShapes,
    staleTime: 60_000,
  });
}

/** A realm's charter (#3983 Plan B Task 4) — the Founder Almanach's Seat
 * liege/realm rail and House chapter's Quiddity prompt. */
export function useCharter(realmId: number | null | undefined) {
  return useQuery({
    queryKey: almanachKeys.charter(realmId ?? 0),
    queryFn: () => fetchCharter(realmId!),
    enabled: realmId != null,
    staleTime: 60_000,
  });
}

/**
 * The one mutation every staff Almanach verb dispatches through (mirrors
 * `useWorldBuilderAction`, `world-builder/queries.ts`): dispatch `key` with
 * whatever kwargs the caller passes to `mutate`, toast the result, and on a
 * real success invalidate every cached Almanach read broadly
 * (`almanachKeys.all` covers the ladder, houses list and document at once —
 * a single verb like `almanach_plant_rung` can move a realm's unclaimed
 * counts and a house's charter together, so a narrower invalidation would
 * risk missing one). A `success: false` dispatch (a business-rule refusal —
 * HTTP 200, see `DispatchResult` in `./api`) toasts an error and skips
 * invalidation instead, so a refused action never looks like it landed.
 */
export function useAlmanachMutation(key: AlmanachActionKey) {
  const queryClient = useQueryClient();
  const characterId = useWorldBuilderActor();
  return useMutation({
    mutationFn: (kwargs: Record<string, unknown>) => {
      if (characterId == null) {
        return Promise.reject(
          new Error(
            'Select a character to build as; almanach actions dispatch through your played character.'
          )
        );
      }
      return dispatchAlmanach(characterId, key, kwargs);
    },
    onSuccess: ({ message, success }) => {
      if (success === false) {
        toast.error(message);
        return;
      }
      toast.success(message);
      queryClient.invalidateQueries({ queryKey: almanachKeys.all });
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });
}

// --- #4239: every family, every person -------------------------------------

export function useFront(q: string) {
  return useQuery({
    queryKey: almanachKeys.front(q),
    queryFn: () => fetchFront(q),
    staleTime: 15_000,
  });
}

/** Search as you type; nothing is fetched under two characters (the server
 * returns nothing for them either). */
export function useSearch(q: string) {
  const trimmed = q.trim();
  return useQuery({
    queryKey: almanachKeys.search(trimmed),
    queryFn: () => fetchSearch(trimmed),
    enabled: trimmed.length >= 2,
    staleTime: 10_000,
  });
}

export function usePersonDocument(personId: number | null | undefined) {
  return useQuery({
    queryKey: almanachKeys.person(personId ?? 0),
    queryFn: () => fetchPersonDocument(personId!),
    enabled: personId != null,
    staleTime: 15_000,
  });
}

export function useTitleDocument(titleId: number | null | undefined) {
  return useQuery({
    queryKey: almanachKeys.title(titleId ?? 0),
    queryFn: () => fetchTitleDocument(titleId!),
    enabled: titleId != null,
    staleTime: 15_000,
  });
}

export function useFamilyDocument(familyId: number | null | undefined) {
  return useQuery({
    queryKey: almanachKeys.family(familyId ?? 0),
    queryFn: () => fetchFamilyDocument(familyId!),
    enabled: familyId != null,
    staleTime: 15_000,
  });
}

export function useFamilyKinds() {
  return useQuery({
    queryKey: almanachKeys.kinds(),
    queryFn: fetchFamilyKinds,
    staleTime: 300_000,
  });
}

export function useTemplates(realmId: number | null | undefined, kindId: number | null) {
  return useQuery({
    queryKey: almanachKeys.templates(realmId ?? 0, kindId),
    queryFn: () => fetchTemplates(realmId!, kindId ?? undefined),
    enabled: realmId != null,
    staleTime: 60_000,
  });
}

export function useUnionKinds(realmId: number | null | undefined) {
  return useQuery({
    queryKey: almanachKeys.unionKinds(realmId ?? null),
    queryFn: () => fetchUnionKinds(realmId ?? undefined),
    staleTime: 60_000,
  });
}

export function useVacantTitles(realmId: number | null | undefined) {
  return useQuery({
    queryKey: almanachKeys.vacantTitles(realmId ?? 0),
    queryFn: () => fetchVacantTitles(realmId!),
    enabled: realmId != null,
    staleTime: 15_000,
  });
}

export function useRealmTitles(realmId: number | null | undefined) {
  return useQuery({
    queryKey: almanachKeys.realmTitles(realmId ?? 0),
    queryFn: () => fetchRealmTitles(realmId!),
    enabled: realmId != null,
    staleTime: 15_000,
  });
}

export function useHoldingKinds() {
  return useQuery({
    queryKey: almanachKeys.holdingKinds(),
    queryFn: fetchHoldingKinds,
    staleTime: 300_000,
  });
}
