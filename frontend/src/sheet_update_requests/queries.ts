/**
 * Sheet update requests — React Query hooks (#2631).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  createUpdateRequest,
  fetchProfileTextVersions,
  listUpdateRequests,
  signoffUpdateRequest,
  withdrawUpdateRequest,
  type ListRequestsParams,
} from './api';
import type { CreateUpdateRequestBody, SignoffBody } from './types';

export const sheetUpdateRequestKeys = {
  all: ['sheet-update-requests'] as const,
  list: (params: ListRequestsParams) => ['sheet-update-requests', 'list', params] as const,
  versions: (sheetId: number) => ['sheet-update-requests', 'versions', sheetId] as const,
};

export function useUpdateRequestsQuery(params: ListRequestsParams, enabled = true) {
  return useQuery({
    queryKey: sheetUpdateRequestKeys.list(params),
    queryFn: () => listUpdateRequests(params),
    enabled,
  });
}

export function useProfileTextVersionsQuery(sheetId: number) {
  return useQuery({
    queryKey: sheetUpdateRequestKeys.versions(sheetId),
    queryFn: () => fetchProfileTextVersions(sheetId),
  });
}

export function useCreateUpdateRequestMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateUpdateRequestBody) => createUpdateRequest(body),
    onSuccess: () => {
      toast.success('Update request submitted to your table GM.');
      void queryClient.invalidateQueries({ queryKey: sheetUpdateRequestKeys.all });
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useSignoffMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: SignoffBody }) => signoffUpdateRequest(id, body),
    onSuccess: (request) => {
      toast.success(request.status === 'rejected' ? 'Request declined.' : 'Request approved.');
      void queryClient.invalidateQueries({ queryKey: sheetUpdateRequestKeys.all });
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useWithdrawMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => withdrawUpdateRequest(id),
    onSuccess: () => {
      toast.success('Request withdrawn.');
      void queryClient.invalidateQueries({ queryKey: sheetUpdateRequestKeys.all });
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
