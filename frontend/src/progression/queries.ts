/**
 * React Query hooks for progression data.
 */

import { useQuery } from '@tanstack/react-query';
import { fetchAccountProgression } from './api';
import { useAccount } from '@/store/hooks';

export function useAccountProgressionQuery() {
  const account = useAccount();
  return useQuery({
    queryKey: ['account-progression'],
    queryFn: fetchAccountProgression,
    enabled: !!account,
  });
}
