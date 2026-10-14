import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useBrowsingIdentity } from '@/roster/useBrowsingIdentity';
import { fetchInvocationOptions, fetchPrayers, fetchVisions, pray, sendVision } from './api';
import type { VisionCreate } from './types';

export const worshipKeys = {
  all: ['worship'] as const,
  visions: (sheetId: number) => ['worship', 'visions', sheetId] as const,
  prayers: (sheetId: number) => ['worship', 'prayers', sheetId] as const,
  invocationOptions: (entryId: number | null | undefined) =>
    ['worship', 'invocation-options', entryId ?? null] as const,
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
