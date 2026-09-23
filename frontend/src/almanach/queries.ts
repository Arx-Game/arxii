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
  fetchHouseDocument,
  fetchHouses,
  fetchLadder,
  fetchLandShapes,
  fetchRealms,
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
  document: (houseId: number) => [...almanachKeys.all, 'document', houseId] as const,
  landShapes: () => [...almanachKeys.all, 'land-shapes'] as const,
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

/** The realm's houses (#3983 Task 8's "a house on record" select). */
export function useHouses(realmId: number | null | undefined) {
  return useQuery({
    queryKey: almanachKeys.houses(realmId ?? 0),
    queryFn: () => fetchHouses(realmId!),
    enabled: realmId != null,
    staleTime: 30_000,
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
