/**
 * Rituals React Query hooks
 *
 * Wraps api.ts functions with React Query hooks.
 * ritualKeys factory provides consistent query keys for cache invalidation.
 *
 * Also covers RitualSession hooks (Covenants Slice B, Phase 9).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from './api';
import type {
  AnimaRitualPatchBody,
  RitualSessionAcceptRequest,
  RitualSessionDraftRequest,
} from './api';
import type { PerformRitualRequest, Ritual } from './types';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const ritualKeys = {
  all: ['rituals'] as const,
  list: () => [...ritualKeys.all, 'list'] as const,
  detail: (id: number) => [...ritualKeys.all, 'detail', id] as const,
};

export const ritualSessionKeys = {
  all: ['ritual-sessions'] as const,
  inbox: () => [...ritualSessionKeys.all, 'inbox'] as const,
  outbox: () => [...ritualSessionKeys.all, 'outbox'] as const,
  detail: (id: number) => [...ritualSessionKeys.all, 'detail', id] as const,
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

// ---------------------------------------------------------------------------
// RitualSession read hooks (Covenants Slice B)
// ---------------------------------------------------------------------------

/**
 * Polls every 5 s — inbox is the primary notification surface for pending invitations.
 * Matches the polling cadence used in magic/queries.ts for active-state checks.
 */
export function useRitualSessionInbox() {
  return useQuery({
    queryKey: ritualSessionKeys.inbox(),
    queryFn: () => api.fetchRitualSessionInbox(),
    staleTime: 5_000,
    refetchInterval: 5_000,
    throwOnError: true,
  });
}

/**
 * Polls every 5 s — outbox lets the initiator watch participant responses in real time.
 */
export function useRitualSessionOutbox() {
  return useQuery({
    queryKey: ritualSessionKeys.outbox(),
    queryFn: () => api.fetchRitualSessionOutbox(),
    staleTime: 5_000,
    refetchInterval: 5_000,
    throwOnError: true,
  });
}

export function useRitualSessionDetail(id: number) {
  return useQuery({
    queryKey: ritualSessionKeys.detail(id),
    queryFn: () => api.fetchRitualSessionDetail(id),
    enabled: id > 0,
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// RitualSession mutation hooks (Covenants Slice B)
// ---------------------------------------------------------------------------

export function useDraftRitualSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RitualSessionDraftRequest) => api.draftRitualSession(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ritualSessionKeys.inbox() });
      void qc.invalidateQueries({ queryKey: ritualSessionKeys.outbox() });
    },
  });
}

export function useAcceptRitualSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: RitualSessionAcceptRequest }) =>
      api.acceptRitualSession(id, body),
    onSuccess: (_data, { id }) => {
      void qc.invalidateQueries({ queryKey: ritualSessionKeys.detail(id) });
      void qc.invalidateQueries({ queryKey: ritualSessionKeys.inbox() });
    },
  });
}

export function useDeclineRitualSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.declineRitualSession(id),
    onSuccess: (_data, id) => {
      void qc.invalidateQueries({ queryKey: ritualSessionKeys.detail(id) });
      void qc.invalidateQueries({ queryKey: ritualSessionKeys.inbox() });
    },
  });
}

export function useFireRitualSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.fireRitualSession(id),
    onSuccess: (_data, id) => {
      void qc.invalidateQueries({ queryKey: ritualSessionKeys.detail(id) });
      void qc.invalidateQueries({ queryKey: ritualSessionKeys.outbox() });
      // NOTE: The fire response does not carry a {result_kind, result_id} envelope
      // in the generated types (it returns RitualSessionList). Covenant query key
      // invalidation is deferred until a covenantKeys factory exists in
      // frontend/src/covenants/. When that ships, add:
      //   if (data.result_kind === 'covenant' || data.result_kind === 'membership') {
      //     void qc.invalidateQueries({ queryKey: covenantKeys.detail(data.result_id) });
      //   }
    },
  });
}

export function useCancelRitualSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.cancelRitualSession(id),
    onSuccess: (_data, id) => {
      void qc.invalidateQueries({ queryKey: ritualSessionKeys.detail(id) });
      void qc.invalidateQueries({ queryKey: ritualSessionKeys.outbox() });
    },
  });
}
