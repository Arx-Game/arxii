/**
 * React Query hooks for the deliberate skill training surface (#3045).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAccount } from '@/store/hooks';
import {
  answerMentoring,
  createTrainingAllocation,
  deleteTrainingAllocation,
  fetchMentoring,
  fetchSkillsCatalog,
  fetchTrainingAllocations,
  updateTrainingAllocation,
} from './api';
import type { MentoringAnswer } from './api';
import type { ManageTrainingAddRequest, PatchedManageTrainingUpdateRequest } from './types';

const TRAINING_ALLOCATIONS_KEY = ['training-allocations'];
// The mentoring list belongs to the account, never to the selected character, so the key
// carries no character id (#5326).
const MENTORING_KEY = ['mentoring'];

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

export function useMentoringQuery() {
  const account = useAccount();
  return useQuery({
    queryKey: MENTORING_KEY,
    queryFn: fetchMentoring,
    enabled: !!account,
  });
}

/** Accept, decline or stop one mentoring row; both lists are refetched after either outcome. */
export function useAnswerMentoringMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ allocationId, answer }: { allocationId: number; answer: MentoringAnswer }) =>
      answerMentoring(allocationId, answer),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: MENTORING_KEY });
      queryClient.invalidateQueries({ queryKey: TRAINING_ALLOCATIONS_KEY });
    },
  });
}
