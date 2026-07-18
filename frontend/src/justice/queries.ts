/**
 * Justice React Query hooks (#1765).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  fetchMyCase,
  fetchPersonaHeat,
  fetchWantedList,
  postBribe,
  postEvidence,
  postLieLow,
  postPardon,
  postTrial,
} from './api';

/** The viewer's own warrant rows — where their active persona is wanted. */
export function usePersonaHeat(viewerEntryId: number | null) {
  return useQuery({
    queryKey: ['justice', 'heat', viewerEntryId],
    queryFn: () => fetchPersonaHeat(viewerEntryId as number),
    enabled: viewerEntryId !== null,
  });
}

export function useWantedList(areaId: number | null, viewerEntryId?: number | null) {
  return useQuery({
    queryKey: ['justice', 'wanted', areaId, viewerEntryId ?? null],
    queryFn: () => fetchWantedList(areaId as number, viewerEntryId),
    enabled: areaId != null,
  });
}

/** The viewer's own awaiting-trial case, if any (#2378). */
export function useMyCase(viewerEntryId: number | null) {
  return useQuery({
    queryKey: ['justice', 'my-case', viewerEntryId],
    queryFn: () => fetchMyCase(viewerEntryId as number),
    enabled: viewerEntryId !== null,
  });
}

export function useSubmitEvidenceMutation(viewerEntryId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ caseId, manufactured }: { caseId: number; manufactured: boolean }) =>
      postEvidence(viewerEntryId as number, caseId, manufactured),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['justice'] }).catch(() => {});
    },
  });
}

export function useInitiateTrialMutation(viewerEntryId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ caseId }: { caseId: number }) => postTrial(viewerEntryId as number, caseId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['justice'] }).catch(() => {});
    },
  });
}

export function usePardonMutation(viewerEntryId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ areaId, targetPersonaId }: { areaId: number; targetPersonaId: number }) =>
      postPardon(viewerEntryId as number, areaId, targetPersonaId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['justice'] }).catch(() => {});
    },
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
