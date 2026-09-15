/**
 * Justice React Query hooks (#1765).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { reactToWindow } from '@/scenes/queries';
import {
  fetchMyCase,
  fetchPersonaHeat,
  fetchWantedList,
  getPendingWitnessWindows,
  postBribe,
  postEvidence,
  postLieLow,
  postPardon,
  postTrial,
} from './api';

export type { PaginatedPendingReactionWindowList, PendingReactionWindow } from './api';

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

// ---------------------------------------------------------------------------
// Witness reaction windows (#2987)
// ---------------------------------------------------------------------------

const pendingWitnessWindowsKey = ['justice', 'reaction-windows', 'pending', 'witness'] as const;

/**
 * Pending witness reaction windows for the active persona. Mounted only inside
 * the active scene view (a witness window can only open there), so the 5 s
 * poll runs only where it matters.
 * throwOnError deliberately NOT set: same rationale as
 * usePendingEntryFlourishOffers (@/magic/queries) - this backs an
 * overlay/strip that must degrade to rendering nothing on fetch errors.
 */
export function usePendingWitnessWindows(enabled: boolean = true) {
  return useQuery({
    queryKey: pendingWitnessWindowsKey,
    queryFn: () => getPendingWitnessWindows(),
    refetchInterval: 5_000,
    enabled,
  });
}

/**
 * React to a pending window with one of its choice slugs, via the shared
 * reactToWindow transport (POST /api/reaction-windows/{id}/react/).
 * On success invalidates the pending inbox so the answered window clears.
 */
export function useReactToWindow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      windowId,
      personaId,
      choice,
    }: {
      windowId: number;
      personaId: number;
      choice: string;
    }) => reactToWindow(windowId, { persona_id: personaId, choice }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: pendingWitnessWindowsKey }).catch(() => {});
    },
  });
}
