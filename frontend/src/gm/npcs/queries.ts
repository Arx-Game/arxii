/**
 * Hooks for the Guide's NPC play UI (#4418): the offers waiting for the Guide, and
 * the answer dispatch. Accepting an offer changes the Guide's playable set, so both
 * the offers list and `mine` are refetched.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { postDispatchAction } from '@/combat/api';
import { isDispatchFailure } from '@/combat/types';
import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import { useAccount } from '@/store/hooks';

/**
 * One row of GET /api/roster/npcs/offers/ (`NPCOfferSerializer`). The generated schema
 * types that route as a single NPCRosterRow, which is wrong for this paginated list,
 * so the row shape is declared here from the serializer.
 */
export interface NpcOffer {
  loan_id: number;
  roster_entry_id: number;
  name: string;
  thumbnail_url: string | null;
  scene_id: number | null;
  scene_title: string | null;
  offered_by_name: string;
  notes_for_player: string;
}

export const npcOfferKeys = {
  offers: ['npc-offers'] as const,
};

async function fetchNpcOffers(): Promise<NpcOffer[]> {
  const res = await apiFetch('/api/roster/npcs/offers/');
  if (!res.ok) await throwApiError(res, 'Failed to load NPC offers');
  const body = (await res.json()) as { results: NpcOffer[] };
  return body.results;
}

/** The OFFERED loans waiting on this Guide. Only a Guide/GM may read them. */
export function useNpcOffersQuery(enabled = true) {
  const account = useAccount();
  return useQuery({
    queryKey: npcOfferKeys.offers,
    queryFn: fetchNpcOffers,
    enabled: !!account && enabled,
    retry: false,
    // A non-Guide's 403 settles as an error and is not polled; a Guide re-reads each minute.
    refetchInterval: (query) => (query.state.status === 'success' ? 60_000 : false),
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
