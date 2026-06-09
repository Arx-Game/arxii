/**
 * React Query hooks for the NPC-services staff editor (#728).
 */
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';

import {
  createMissionDetails,
  createOffer,
  createRole,
  deleteOffer,
  deleteRole,
  getRole,
  listMissionDetails,
  listOffers,
  listRoles,
  patchMissionDetails,
  patchOffer,
  patchRole,
} from './api';
import type {
  MissionOfferDetailsRequest,
  NPCRoleFilters,
  NPCRoleRequest,
  NPCServiceOfferRequest,
  PaginatedResponse,
  NPCRole,
  NPCServiceOffer,
  MissionOfferDetails,
} from './types';

export const npcServiceKeys = {
  all: ['npc-services'] as const,
  roles: () => [...npcServiceKeys.all, 'roles'] as const,
  roleList: (filters: NPCRoleFilters) => [...npcServiceKeys.roles(), 'list', filters] as const,
  roleDetail: (id: number) => [...npcServiceKeys.roles(), 'detail', id] as const,
  offers: () => [...npcServiceKeys.all, 'offers'] as const,
  offerList: (roleId: number) => [...npcServiceKeys.offers(), 'list', roleId] as const,
  missionDetails: () => [...npcServiceKeys.all, 'mission-details'] as const,
  missionDetailList: (roleId: number) =>
    [...npcServiceKeys.missionDetails(), 'list', roleId] as const,
};

export function useRoles(filters: NPCRoleFilters = {}): UseQueryResult<PaginatedResponse<NPCRole>> {
  return useQuery({
    queryKey: npcServiceKeys.roleList(filters),
    queryFn: () => listRoles(filters),
    staleTime: 30_000,
  });
}

export function useRole(id: number | null): UseQueryResult<NPCRole> {
  return useQuery({
    queryKey: npcServiceKeys.roleDetail(id ?? -1),
    queryFn: () => getRole(id as number),
    enabled: id !== null,
  });
}

export function useOffersForRole(
  roleId: number | null
): UseQueryResult<PaginatedResponse<NPCServiceOffer>> {
  return useQuery({
    queryKey: npcServiceKeys.offerList(roleId ?? -1),
    queryFn: () => listOffers({ role: roleId as number, page_size: 200 }),
    enabled: roleId !== null,
  });
}

export function useMissionDetailsForRole(
  roleId: number | null
): UseQueryResult<PaginatedResponse<MissionOfferDetails>> {
  return useQuery({
    queryKey: npcServiceKeys.missionDetailList(roleId ?? -1),
    queryFn: () => listMissionDetails({ role: roleId as number, page_size: 200 }),
    enabled: roleId !== null,
  });
}

export function useCreateRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: NPCRoleRequest) => createRole(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: npcServiceKeys.roles() }),
  });
}

export function usePatchRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<NPCRoleRequest> }) =>
      patchRole(id, body),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: npcServiceKeys.roleDetail(id) });
      qc.invalidateQueries({ queryKey: npcServiceKeys.roles() });
    },
  });
}

export function useDeleteRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteRole(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: npcServiceKeys.roles() }),
  });
}

function invalidateRoleOffers(qc: ReturnType<typeof useQueryClient>, roleId: number) {
  qc.invalidateQueries({ queryKey: npcServiceKeys.offerList(roleId) });
  qc.invalidateQueries({ queryKey: npcServiceKeys.missionDetailList(roleId) });
}

export function useCreateOffer(roleId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: NPCServiceOfferRequest) => createOffer(body),
    onSuccess: () => invalidateRoleOffers(qc, roleId),
  });
}

export function usePatchOffer(roleId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<NPCServiceOfferRequest> }) =>
      patchOffer(id, body),
    onSuccess: () => invalidateRoleOffers(qc, roleId),
  });
}

export function useDeleteOffer(roleId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteOffer(id),
    onSuccess: () => invalidateRoleOffers(qc, roleId),
  });
}

export function useCreateMissionDetails(roleId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: MissionOfferDetailsRequest) => createMissionDetails(body),
    onSuccess: () => invalidateRoleOffers(qc, roleId),
  });
}

export function usePatchMissionDetails(roleId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<MissionOfferDetailsRequest> }) =>
      patchMissionDetails(id, body),
    onSuccess: () => invalidateRoleOffers(qc, roleId),
  });
}
