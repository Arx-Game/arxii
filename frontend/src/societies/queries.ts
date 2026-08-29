import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { fetchPendingMembershipOffers, respondToMembershipOffer } from './api';
import type { OfferResponse } from './types';
import { useAccount } from '@/store/hooks';

export const societiesKeys = {
  all: ['societies'] as const,
  pendingOffers: () => [...societiesKeys.all, 'pending-offers'] as const,
};

/** Pending org membership offers visible to the account (#3412 — Hall Attention band). */
export function usePendingMembershipOffersQuery() {
  const account = useAccount();
  return useQuery({
    queryKey: societiesKeys.pendingOffers(),
    queryFn: fetchPendingMembershipOffers,
    enabled: !!account,
  });
}

export function useRespondToMembershipOffer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ offerId, response }: { offerId: number; response: OfferResponse }) =>
      respondToMembershipOffer(offerId, response),
    onSuccess: (_data, { response }) => {
      queryClient.invalidateQueries({ queryKey: societiesKeys.pendingOffers() }).catch(() => {});
      toast.success(response === 'accept' ? 'Offer accepted' : 'Offer declined');
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });
}
