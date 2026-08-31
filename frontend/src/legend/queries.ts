/**
 * React Query hooks for the legend module (#3466 Task 10) — the deed page and honor form.
 *
 * Query keys are namespaced `['legend', ...]` per the task brief.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';
import type { HonorDeedRequest } from './api';

export const legendKeys = {
  all: ['legend'] as const,
  deeds: () => [...legendKeys.all, 'deed'] as const,
  deed: (id: number) => [...legendKeys.deeds(), id] as const,
};

/** GET /api/societies/deeds/{id}/ — a deed, its honors, and the viewer's `can_honor`. */
export function useDeed(id: number | null | undefined) {
  return useQuery({
    queryKey: legendKeys.deed(id ?? -1),
    queryFn: () => api.fetchDeed(id as number),
    enabled: id != null,
  });
}

/**
 * POST /api/societies/deeds/{id}/honor/ — amplify a deed by writing a paid, public
 * honor journal. Invalidates the deed's own detail query on success so the new honor,
 * the updated `headroom`, and the viewer's now-changed `can_honor` (already honored,
 * possibly newly at-ceiling) all refresh without a manual refetch.
 */
export function useHonorDeed(deedId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: HonorDeedRequest) => api.honorDeed(deedId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: legendKeys.deed(deedId) }).catch(() => {});
    },
  });
}
