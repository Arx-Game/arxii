/**
 * Justice React Query hooks (#1765).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { fetchPersonaHeat, fetchWantedList, postBribe, postLieLow } from './api';

/** The viewer's own warrant rows — where their active persona is wanted. */
export function usePersonaHeat(viewerEntryId: number | null) {
  return useQuery({
    queryKey: ['justice', 'heat', viewerEntryId],
    queryFn: () => fetchPersonaHeat(viewerEntryId as number),
    enabled: viewerEntryId !== null,
  });
}

export function useWantedList(areaId: number | null) {
  return useQuery({
    queryKey: ['justice', 'wanted', areaId],
    queryFn: () => fetchWantedList(areaId as number),
    enabled: areaId != null,
  });
}

export function useLieLowMutation(viewerEntryId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ areaId, end }: { areaId: number; end?: boolean }) =>
      postLieLow(viewerEntryId as number, areaId, end ?? false),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['justice'] }).catch(() => {});
    },
  });
}

export function useBribeMutation(viewerEntryId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ areaId }: { areaId: number }) => postBribe(viewerEntryId as number, areaId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['justice'] }).catch(() => {});
    },
  });
}
