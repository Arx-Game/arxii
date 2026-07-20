import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAccount } from '@/store/hooks';
import * as api from './api';

export const ceremonyKeys = {
  all: ['ceremonies'] as const,
  seanceOffers: () => [...ceremonyKeys.all, 'seance-offers'] as const,
};

/** Gates on account only — NOT on available_characters.length (see the
 * plan's Task 10 note: a retired-only account has zero available
 * characters, and is exactly who most needs this list). */
export function useSeanceOffers() {
  const account = useAccount();
  return useQuery({
    queryKey: ceremonyKeys.seanceOffers(),
    queryFn: () => api.getSeanceOffers(),
    enabled: !!account,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
}

export function useRespondToSeanceOffer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ offerId, accept }: { offerId: number; accept: boolean }) =>
      accept ? api.acceptSeanceOffer(offerId) : api.declineSeanceOffer(offerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ceremonyKeys.seanceOffers() });
    },
  });
}
