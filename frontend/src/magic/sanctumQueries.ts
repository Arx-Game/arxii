/**
 * TanStack Query hooks for the Sanctum subsystem.
 *
 * Read: useSanctums (list).
 * Mutations: useHomecoming, usePurging, useWeaveSanctumThread, useSeverSanctumThread.
 * Each mutation invalidates `sanctumKeys.list()` so the dashboard refreshes
 * its derived values (homecoming_sum, last ritual timestamps, resonance type).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './sanctumApi';
import type { HomecomingRequest, PurgingRequest, WeaveRequest } from './sanctumTypes';

export const sanctumKeys = {
  all: ['magic', 'sanctums'] as const,
  list: () => [...sanctumKeys.all, 'list'] as const,
};

export function useSanctums() {
  return useQuery({
    queryKey: sanctumKeys.list(),
    queryFn: api.getSanctums,
    throwOnError: true,
  });
}

export function useHomecoming(featureInstanceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: HomecomingRequest) => api.performHomecoming(featureInstanceId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: sanctumKeys.list() }),
  });
}

export function usePurging(featureInstanceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PurgingRequest) => api.performPurging(featureInstanceId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: sanctumKeys.list() }),
  });
}

export function useWeaveSanctumThread(featureInstanceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WeaveRequest) => api.weaveSanctumThread(featureInstanceId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: sanctumKeys.list() }),
  });
}

export function useSeverSanctumThread(featureInstanceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (threadId: number) => api.severSanctumThread(featureInstanceId, threadId),
    onSuccess: () => qc.invalidateQueries({ queryKey: sanctumKeys.list() }),
  });
}

export function useAbsorb(featureInstanceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.absorbSanctumPool(featureInstanceId),
    onSuccess: () => qc.invalidateQueries({ queryKey: sanctumKeys.list() }),
  });
}
