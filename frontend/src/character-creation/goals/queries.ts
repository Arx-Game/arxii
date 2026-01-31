import { useQuery } from '@tanstack/react-query';
import { fetchGoalDomains } from './api';
import type { GoalDomain } from './types';

export const goalKeys = {
  all: ['goals'] as const,
  domains: () => [...goalKeys.all, 'domains'] as const,
};

/**
 * Hook to fetch goal domains.
 */
export function useGoalDomains() {
  return useQuery<GoalDomain[]>({
    queryKey: goalKeys.domains(),
    queryFn: fetchGoalDomains,
    staleTime: 1000 * 60 * 60, // 1 hour - domains rarely change
  });
}
