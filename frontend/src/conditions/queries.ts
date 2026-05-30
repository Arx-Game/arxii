/**
 * Conditions React Query hooks.
 *
 * Backs the condition-detail modal deep link (#551).
 */

import { useQuery } from '@tanstack/react-query';
import { fetchConditionInstance } from './api';

/**
 * Fetch a single condition instance by pk.
 * Disabled when id is null (modal closed).
 */
export function useConditionInstance(id: number | null) {
  return useQuery({
    queryKey: ['conditionInstance', id],
    queryFn: () => fetchConditionInstance(id as number),
    enabled: id != null,
    staleTime: 30_000,
  });
}
