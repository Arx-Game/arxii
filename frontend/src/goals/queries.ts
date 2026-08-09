/**
 * React Query hooks for the goal-log affordance (#3045).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchGoalDomains } from '@/character-creation/goals/api';
import { useAccount } from '@/store/hooks';
import { createGoalJournalEntry, fetchMyGoals } from './api';
import type { CreateGoalJournalRequest } from './types';

export function useGoalDomainsQuery() {
  const account = useAccount();
  return useQuery({
    queryKey: ['goal-domains'],
    queryFn: fetchGoalDomains,
    enabled: !!account,
  });
}

export function useMyGoalsQuery(characterId: number) {
  return useQuery({
    queryKey: ['my-goals', characterId],
    queryFn: () => fetchMyGoals(characterId),
    enabled: characterId > 0,
  });
}

export function useCreateGoalJournalMutation(characterId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateGoalJournalRequest) => createGoalJournalEntry(characterId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-goals', characterId] });
      queryClient.invalidateQueries({ queryKey: ['account-progression'] });
    },
  });
}
