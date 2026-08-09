/**
 * React Query hooks for the deliberate skill training surface (#3045).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAccount } from '@/store/hooks';
import {
  createTrainingAllocation,
  deleteTrainingAllocation,
  fetchSkillsCatalog,
  fetchTrainingAllocations,
  updateTrainingAllocation,
} from './api';
import type { ManageTrainingAddRequest, PatchedManageTrainingUpdateRequest } from './types';

const TRAINING_ALLOCATIONS_KEY = ['training-allocations'];

export function useSkillsCatalogQuery() {
  const account = useAccount();
  return useQuery({
    queryKey: ['skills-catalog'],
    queryFn: fetchSkillsCatalog,
    enabled: !!account,
  });
}

export function useTrainingAllocationsQuery() {
  const account = useAccount();
  return useQuery({
    queryKey: TRAINING_ALLOCATIONS_KEY,
    queryFn: fetchTrainingAllocations,
    enabled: !!account,
  });
}

export function useCreateTrainingAllocationMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ManageTrainingAddRequest) => createTrainingAllocation(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TRAINING_ALLOCATIONS_KEY });
    },
  });
}

export function useUpdateTrainingAllocationMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: PatchedManageTrainingUpdateRequest }) =>
      updateTrainingAllocation(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TRAINING_ALLOCATIONS_KEY });
    },
  });
}

export function useDeleteTrainingAllocationMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteTrainingAllocation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TRAINING_ALLOCATIONS_KEY });
    },
  });
}
