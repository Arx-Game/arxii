/**
 * The draft's distinctions and CG points as the page shows them (#5141).
 *
 * A clicked card shows at once (#5134), so everything that counts the picks has to move
 * with it: the life page's ledger, its totals, the "CG points" lines of the Lineage
 * record and the Gift summary. The draft's own `cg_points_spent` cannot do that. It is
 * the server's sum, and the draft is fetched again only after a save has answered, so
 * for the length of the save plus the heaviest request on the page the totals named a
 * list the cards no longer showed.
 *
 * The sum is re-priced here instead. Every saved pick carries the price the server
 * charged for it, and the draft carries the list its totals were added up from
 * (`draft_data.distinctions`). So: the draft's total, less the prices in the draft's own
 * list, plus the prices in the list on screen (each less the part of the feature
 * qualities the free allowance covers, #5241). With no save in flight the list on screen
 * is the draft's own and the totals are the server's, untouched (`useSyncDistinctions`
 * writes a save's answer into the cached draft the moment it lands).
 */

import { useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useDraftDistinctions, usePendingSync } from '@/hooks/useDistinctions';
import {
  chargedCost,
  featureCost,
  shownPicks,
  type ShownPick,
} from './components/offers/syncHelpers';
import { characterCreationKeys } from './queries';
import type { CharacterDraft, OffersResponse } from './types';

export interface ShownPoints {
  /** The picks on screen: the saved list, with a save in flight laid over it. */
  picks: ShownPick[];
  spent: number;
  remaining: number;
  /** What the feature qualities on screen cost, before the free allowance (#5241). */
  featureSpent: number;
}

export function useShownPicks(draft: CharacterDraft): ShownPoints {
  const { data: saved } = useDraftDistinctions(draft.id);
  const pending = usePendingSync(draft.id);
  const queryClient = useQueryClient();

  return useMemo(() => {
    if (pending === null) {
      return {
        picks: shownPicks(saved, null, () => undefined),
        spent: draft.cg_points_spent,
        remaining: draft.cg_points_remaining,
        featureSpent: draft.feature_points_spent,
      };
    }
    // A card can only be clicked once its chapter's offers are on the page, so the
    // price of a new pick is already in the offers this draft has cached.
    const perRank = new Map<number, number>();
    const cached = queryClient.getQueriesData<OffersResponse>({
      queryKey: [...characterCreationKeys.all, 'draft-offers', draft.id],
    });
    for (const [, chapter] of cached) {
      for (const offer of chapter?.offers ?? []) perRank.set(offer.offer_id, offer.cost_per_rank);
    }
    const picks = shownPicks(saved, pending, (offerId) => perRank.get(offerId));
    // The first points of feature qualities are free (#5241), so a tier that moves
    // inside the allowance moves no CG points; the allowance is taken off both sums.
    const free = draft.feature_points_free;
    const moved = chargedCost(picks, free) - chargedCost(draft.draft_data.distinctions, free);
    return {
      picks,
      spent: draft.cg_points_spent + moved,
      remaining: draft.cg_points_remaining - moved,
      featureSpent: featureCost(picks),
    };
  }, [draft, saved, pending, queryClient]);
}
