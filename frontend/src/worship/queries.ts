import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useBrowsingIdentity } from '@/roster/useBrowsingIdentity';
import {
  closePledge,
  fetchHolySites,
  fetchInvocationOptions,
  fetchPledgeCards,
  fetchPledges,
  fetchPrayers,
  fetchServiceTerms,
  fetchVisions,
  pray,
  sacrifice,
  sendVision,
  takePledge,
} from './api';
import type { VisionCreate } from './types';

export const worshipKeys = {
  all: ['worship'] as const,
  visions: (sheetId: number) => ['worship', 'visions', sheetId] as const,
  prayers: (sheetId: number) => ['worship', 'prayers', sheetId] as const,
  invocationOptions: (entryId: number | null | undefined) =>
    ['worship', 'invocation-options', entryId ?? null] as const,
  pledges: (beingId: number) => ['worship', 'pledges', beingId] as const,
  serviceTerms: (beingId: number, entryId: number | null | undefined) =>
    ['worship', 'service-terms', beingId, entryId ?? null] as const,
  holySites: (entryId: number | null | undefined, roomId: number | null | undefined) =>
    ['worship', 'holy-sites', entryId ?? null, roomId ?? null] as const,
  pledgeCards: (sheetId: number) => ['worship', 'pledge-cards', sheetId] as const,
};

/**
 * The Call on favor picker's data (#4333). Fetched when the picker opens; uses left change
 * with every invocation, so it is never cached for long. `entryId` names the character acting
 * (the scene's active character); omitted, this tab's browsing identity answers, as the
 * mission journal does.
 */
export function useInvocationOptions({
  entryId,
  enabled = true,
}: { entryId?: number | null; enabled?: boolean } = {}) {
  const browsing = useBrowsingIdentity();
  const actingEntryId = entryId === undefined ? browsing.entryId : entryId;
  return useQuery({
    queryKey: worshipKeys.invocationOptions(actingEntryId),
    queryFn: () => fetchInvocationOptions(actingEntryId),
    enabled,
    staleTime: 0,
  });
}

/** The visions sent to one character; the server returns none for a sheet you do not play. */
export function useVisions(sheetId: number, enabled = true) {
  return useQuery({
    queryKey: worshipKeys.visions(sheetId),
    queryFn: () => fetchVisions(sheetId),
    enabled: enabled && sheetId > 0,
  });
}

/** One character's prayers: their own to the owner, anyone's to staff. */
export function usePrayers(sheetId: number, enabled = true) {
  return useQuery({
    queryKey: worshipKeys.prayers(sheetId),
    queryFn: () => fetchPrayers(sheetId),
    enabled: enabled && sheetId > 0,
  });
}

export function usePrayMutation(characterId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ being, text }: { being: number; text: string }) =>
      pray(characterId, being, text),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: worshipKeys.all }).catch(() => {});
    },
  });
}

export function useSendVision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: VisionCreate) => sendVision(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: worshipKeys.all }).catch(() => {});
    },
  });
}

/** The pledge types a being offers (#4333). */
export function usePledges(beingId: number | null, enabled = true) {
  return useQuery({
    queryKey: worshipKeys.pledges(beingId ?? 0),
    queryFn: () => fetchPledges(beingId as number),
    enabled: enabled && beingId != null && beingId > 0,
  });
}

/**
 * What earns favor with a being for a character, and their earning rate (#4333). `sheetId`
 * names a sheet the viewer plays (the sheet page); otherwise this tab's acting character.
 */
export function useServiceTerms(
  beingId: number | null,
  { sheetId, enabled = true }: { sheetId?: number | null; enabled?: boolean } = {}
) {
  const browsing = useBrowsingIdentity();
  const entryId = sheetId != null ? null : browsing.entryId;
  return useQuery({
    queryKey: [...worshipKeys.serviceTerms(beingId ?? 0, entryId), sheetId ?? null],
    queryFn: () => fetchServiceTerms(beingId as number, { sheetId, entryId }),
    enabled: enabled && beingId != null && beingId > 0,
  });
}

/**
 * The beings holy where the acting character stands (#4333): shrine here, temple over it.
 * `roomId` keys the cache to the room, so moving refetches.
 */
export function useHolySites({
  entryId,
  roomId,
  enabled = true,
}: { entryId?: number | null; roomId?: number | null; enabled?: boolean } = {}) {
  const browsing = useBrowsingIdentity();
  const actingEntryId = entryId === undefined ? browsing.entryId : entryId;
  return useQuery({
    queryKey: worshipKeys.holySites(actingEntryId, roomId),
    queryFn: () => fetchHolySites(actingEntryId),
    enabled,
  });
}

/** One character's pledges, newest first; the server returns none for a sheet you do not play. */
export function usePledgeCards(sheetId: number, enabled = true) {
  return useQuery({
    queryKey: worshipKeys.pledgeCards(sheetId),
    queryFn: () => fetchPledgeCards(sheetId),
    enabled: enabled && sheetId > 0,
  });
}

function useWorshipMutation<TVars>(
  mutationFn: (vars: TVars) => ReturnType<typeof pray>,
  extraKeys: readonly (readonly unknown[])[] = []
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: worshipKeys.all }).catch(() => {});
      for (const key of extraKeys) {
        queryClient.invalidateQueries({ queryKey: key }).catch(() => {});
      }
    },
  });
}

export function useTakePledge(characterId: number) {
  return useWorshipMutation(({ pledge, prayer }: { pledge: number; prayer: string }) =>
    takePledge(characterId, pledge, prayer)
  );
}

export function useClosePledge(characterId: number) {
  return useWorshipMutation(
    ({ itemIds }: { itemIds: number[] }) => closePledge(characterId, itemIds),
    [['inventory', characterId]]
  );
}

export function useSacrifice(characterId: number) {
  return useWorshipMutation(
    ({ itemIds, being }: { itemIds: number[]; being?: number | null }) =>
      sacrifice(characterId, itemIds, being),
    [['inventory', characterId]]
  );
}
