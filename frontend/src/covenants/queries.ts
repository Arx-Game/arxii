/**
 * Covenants React Query hooks
 *
 * Covers covenant reads and character role engage/disengage mutations.
 * Implements Phase 9 Tasks 9.6 (covenant pages).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from './api';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const covenantKeys = {
  all: ['covenants'] as const,
  list: () => [...covenantKeys.all, 'list'] as const,
  detail: (id: number) => [...covenantKeys.all, 'detail', id] as const,
  members: (covenantId: number) => [...covenantKeys.all, 'members', covenantId] as const,
};

// ---------------------------------------------------------------------------
// Read hooks
// ---------------------------------------------------------------------------

export function useCovenants() {
  return useQuery({
    queryKey: covenantKeys.list(),
    queryFn: () => api.getCovenants(),
    throwOnError: true,
  });
}

export function useCovenantDetail(id: number) {
  return useQuery({
    queryKey: covenantKeys.detail(id),
    queryFn: () => api.getCovenant(id),
    enabled: id > 0,
    throwOnError: true,
  });
}

export function useCovenantMembers(covenantId: number) {
  return useQuery({
    queryKey: covenantKeys.members(covenantId),
    queryFn: () => api.getCharacterRolesForCovenant(covenantId),
    enabled: covenantId > 0,
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

export function useEngageMembership(covenantId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (membershipId: number) => api.engageMembership(membershipId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: covenantKeys.members(covenantId) });
      void qc.invalidateQueries({ queryKey: covenantKeys.detail(covenantId) });
    },
  });
}

export function useDisengageMembership(covenantId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (membershipId: number) => api.disengageMembership(membershipId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: covenantKeys.members(covenantId) });
      void qc.invalidateQueries({ queryKey: covenantKeys.detail(covenantId) });
    },
  });
}
