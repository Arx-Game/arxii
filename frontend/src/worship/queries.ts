import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchPrayers, fetchVisions, pray, sendVision } from './api';
import type { VisionCreate } from './types';

export const worshipKeys = {
  all: ['worship'] as const,
  visions: (sheetId: number) => ['worship', 'visions', sheetId] as const,
  prayers: (sheetId: number) => ['worship', 'prayers', sheetId] as const,
};

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
