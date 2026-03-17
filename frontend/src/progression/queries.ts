/**
 * React Query hooks for progression data.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { claimKudosForXP, fetchAccountProgression } from './api';
import { useAccount } from '@/store/hooks';

export function useAccountProgressionQuery() {
  const account = useAccount();
  return useQuery({
    queryKey: ['account-progression'],
    queryFn: fetchAccountProgression,
    enabled: !!account,
  });
}

export function useClaimKudosMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimCategoryId, amount }: { claimCategoryId: number; amount: number }) =>
      claimKudosForXP(claimCategoryId, amount),
    onSuccess: (data) => {
      queryClient.setQueryData(['account-progression'], data);
    },
  });
}
