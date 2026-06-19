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
  powers: (covenantId: number) => [...covenantKeys.all, 'powers', covenantId] as const,
  subroles: (parentRoleId: number) => [...covenantKeys.all, 'subroles', parentRoleId] as const,
  ranks: (covenantId: number) => [...covenantKeys.all, 'ranks', covenantId] as const,
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

export function useCovenantPowers(covenantId: number) {
  return useQuery({
    queryKey: covenantKeys.powers(covenantId),
    queryFn: () => api.getCovenantPowers(covenantId),
    enabled: covenantId > 0,
    throwOnError: true,
  });
}

/**
 * Fetch a role's sub-roles for the promotion picker. Disabled until a parent
 * role id is known.
 */
export function useSubroles(parentRoleId: number | null) {
  return useQuery({
    queryKey: covenantKeys.subroles(parentRoleId ?? 0),
    queryFn: () => api.getCovenantRoles({ parent_role: parentRoleId as number }),
    enabled: parentRoleId != null,
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
      qc.invalidateQueries({ queryKey: covenantKeys.members(covenantId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: covenantKeys.detail(covenantId) }).catch(() => {});
    },
  });
}

export function useDisengageMembership(covenantId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (membershipId: number) => api.disengageMembership(membershipId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: covenantKeys.members(covenantId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: covenantKeys.detail(covenantId) }).catch(() => {});
    },
  });
}

export function useLeaveMembership(covenantId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (membershipId: number) => api.leaveMembership(membershipId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: covenantKeys.members(covenantId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: covenantKeys.detail(covenantId) }).catch(() => {});
    },
  });
}

export function useKickMember(covenantId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (membershipId: number) => api.kickMember(membershipId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: covenantKeys.members(covenantId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: covenantKeys.detail(covenantId) }).catch(() => {});
    },
  });
}

export function usePromoteMembership(covenantId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { membershipId: number; targetSubroleId: number }) =>
      api.promoteMembership(vars.membershipId, vars.targetSubroleId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: covenantKeys.members(covenantId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: covenantKeys.detail(covenantId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: covenantKeys.powers(covenantId) }).catch(() => {});
    },
  });
}

export function useStandDownCovenant(covenantId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.standDownCovenant(covenantId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: covenantKeys.detail(covenantId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: covenantKeys.powers(covenantId) }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Rank hooks
// ---------------------------------------------------------------------------

export function useCovenantRanks(covenantId: number) {
  return useQuery({
    queryKey: covenantKeys.ranks(covenantId),
    queryFn: () => api.getCovenantRanksForCovenant(covenantId),
    enabled: covenantId > 0,
    throwOnError: true,
  });
}

export function useCreateRank(covenantId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      covenant: number;
      name: string;
      tier: number;
      description?: string;
      can_invite?: boolean;
      can_kick?: boolean;
      can_manage_ranks?: boolean;
    }) => api.createCovenantRank(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: covenantKeys.ranks(covenantId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: covenantKeys.members(covenantId) }).catch(() => {});
    },
  });
}

export function useUpdateRank(covenantId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      id: number;
      data: Partial<{
        name: string;
        description: string;
        can_invite: boolean;
        can_kick: boolean;
        can_manage_ranks: boolean;
      }>;
    }) => api.updateCovenantRank(vars.id, vars.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: covenantKeys.ranks(covenantId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: covenantKeys.members(covenantId) }).catch(() => {});
    },
  });
}

export function useDeleteRank(covenantId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { rankId: number; reassignTo: number }) =>
      api.deleteCovenantRank(vars.rankId, vars.reassignTo),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: covenantKeys.ranks(covenantId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: covenantKeys.members(covenantId) }).catch(() => {});
    },
  });
}

export function useAssignMemberToRank(covenantId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { rankId: number; membershipId: number }) =>
      api.assignMemberToRank(vars.rankId, vars.membershipId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: covenantKeys.members(covenantId) }).catch(() => {});
    },
  });
}

export function useReorderRanks(covenantId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { orderedRankIds: number[] }) =>
      api.reorderRanks(covenantId, vars.orderedRankIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: covenantKeys.ranks(covenantId) }).catch(() => {});
    },
  });
}
