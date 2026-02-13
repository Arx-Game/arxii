import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { PaginatedResponse } from '@/shared/types';
import type { DraftApplication } from '@/character-creation/types';
import {
  addStaffComment,
  approveApplication,
  claimApplication,
  denyApplication,
  getApplicationDetail,
  getApplications,
  getPendingApplicationCount,
  requestApplicationRevisions,
} from '@/character-creation/api';

export const staffKeys = {
  all: ['staff'] as const,
  applications: (status?: string) => [...staffKeys.all, 'applications', status] as const,
  application: (id: number) => [...staffKeys.all, 'application', id] as const,
  pendingCount: () => [...staffKeys.all, 'pending-count'] as const,
};

export function useApplications(statusFilter?: string) {
  return useQuery<PaginatedResponse<DraftApplication>>({
    queryKey: staffKeys.applications(statusFilter),
    queryFn: () => getApplications(statusFilter),
  });
}

export function useApplicationDetail(id: number | undefined) {
  return useQuery({
    queryKey: staffKeys.application(id!),
    queryFn: () => getApplicationDetail(id!),
    enabled: !!id,
  });
}

export function usePendingApplicationCount(enabled = true) {
  return useQuery({
    queryKey: staffKeys.pendingCount(),
    queryFn: getPendingApplicationCount,
    refetchInterval: 60_000,
    enabled,
  });
}

export function useClaimApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: claimApplication,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: staffKeys.all });
    },
  });
}

export function useApproveApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, comment }: { id: number; comment?: string }) =>
      approveApplication(id, comment),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: staffKeys.all });
    },
  });
}

export function useRequestRevisions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, comment }: { id: number; comment: string }) =>
      requestApplicationRevisions(id, comment),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: staffKeys.all });
    },
  });
}

export function useDenyApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, comment }: { id: number; comment: string }) => denyApplication(id, comment),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: staffKeys.all });
    },
  });
}

export function useAddStaffComment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, text }: { id: number; text: string }) => addStaffComment(id, text),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: staffKeys.application(id) });
    },
  });
}
