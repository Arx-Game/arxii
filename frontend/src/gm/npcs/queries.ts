/**
 * Hooks for the Guide's NPC play UI (#4418): the offers waiting for the Guide, and
 * the answer dispatch. Accepting an offer changes the Guide's playable set, so both
 * the offers list and `mine` are refetched.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import type { components } from '@/generated/api';
import { postDispatchAction } from '@/combat/api';
import { isDispatchFailure } from '@/combat/types';
import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import { useAccount } from '@/store/hooks';

export type NpcOffer = components['schemas']['NPCOffer'];

export const npcOfferKeys = {
  offers: ['npc-offers'] as const,
};

async function fetchNpcOffers(): Promise<NpcOffer[]> {
  const res = await apiFetch('/api/roster/npcs/offers/');
  if (!res.ok) await throwApiError(res, 'Failed to load NPC offers');
  const body = (await res.json()) as components['schemas']['PaginatedNPCOfferList'];
  return body.results;
}

/** The OFFERED loans waiting on this Guide. Only staff, GMs and Guides may read them. */
export function useNpcOffersQuery() {
  const account = useAccount();
  const mayBeOffered = Boolean(account && (account.is_staff || account.is_gm || account.is_guide));
  return useQuery({
    queryKey: npcOfferKeys.offers,
    queryFn: fetchNpcOffers,
    enabled: mayBeOffered,
    retry: false,
    // A non-Guide's 403 settles as an error and is not polled; a Guide re-reads every 30s
    // and on focus (nothing pushes a new offer or a withdrawn one).
    refetchInterval: (query) => (query.state.status === 'success' ? 30_000 : false),
    refetchOnWindowFocus: true,
  });
}

/** Accept or decline an offered NPC through the `answer_npc_loan` registry action. */
export function useAnswerNpcLoan(characterId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ loanId, accept }: { loanId: number; accept: boolean }) =>
      postDispatchAction(characterId, {
        ref: { backend: 'registry', registry_key: 'answer_npc_loan' },
        kwargs: { loan_id: loanId, accept },
      }),
    onSuccess: (result) => {
      if (isDispatchFailure(result)) {
        toast.error(result.message ?? "Couldn't answer that offer.");
      }
    },
    onError: (error: Error) => toast.error(error.message),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: npcOfferKeys.offers });
      void queryClient.invalidateQueries({ queryKey: ['my-roster-entries'] });
    },
  });
}
