/**
 * Rituals React Query hooks
 *
 * Wraps api.ts functions with React Query hooks.
 * ritualKeys factory provides consistent query keys for cache invalidation.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from './api';
import type { AnimaRitualPatchBody } from './api';
import type { PerformRitualRequest, Ritual } from './types';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const ritualKeys = {
  all: ['rituals'] as const,
  list: () => [...ritualKeys.all, 'list'] as const,
  detail: (id: number) => [...ritualKeys.all, 'detail', id] as const,
};

// ---------------------------------------------------------------------------
// Read hooks
// ---------------------------------------------------------------------------

export function useRituals() {
  return useQuery({
    queryKey: ritualKeys.list(),
    queryFn: () => api.getRituals(),
    throwOnError: true,
  });
}

export function useRitual(id: number) {
  return useQuery({
    queryKey: ritualKeys.detail(id),
    queryFn: () => api.getRitual(id),
    enabled: id > 0,
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

export function usePerformRitual() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PerformRitualRequest) => api.performRitual(body),
    onSuccess: () => {
      // Invalidate ritual list in case ritual state changes are reflected there,
      // and the broad 'all' key so any downstream ritual-affected data refreshes.
      void qc.invalidateQueries({ queryKey: ritualKeys.list() });
      void qc.invalidateQueries({ queryKey: ritualKeys.all });
    },
  });
}

export function usePatchRitual() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: AnimaRitualPatchBody }) =>
      api.patchRitual(id, body),
    onSuccess: (data: Ritual) => {
      void qc.invalidateQueries({ queryKey: ritualKeys.detail(data.id) });
      void qc.invalidateQueries({ queryKey: ritualKeys.list() });
    },
  });
}
