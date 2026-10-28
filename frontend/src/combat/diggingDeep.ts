/** Helpers for digging deep (#4738): the dispatch request and the cost label. */

import type { components } from '@/generated/api';
import type { DispatchActionRequest } from './types';

type DigDeepOffer = components['schemas']['DigDeepOffer'];

export const DIG_DEEP_REGISTRY_KEY = 'combat_dig_deep';

/** A `combat_dig_deep` registry dispatch. */
export function digDeepRequest(): DispatchActionRequest {
  return { ref: { backend: 'registry', registry_key: DIG_DEEP_REGISTRY_KEY }, kwargs: {} };
}

/** "Free" while a free dig deep is held, else "Costs mental fatigue 3". */
export function digDeepCostLabel(offer: DigDeepOffer): string {
  if (offer.free_dig_deeps > 0) return 'Free';
  return `Costs ${offer.fatigue_category} fatigue ${offer.fatigue_cost}`;
}

/** "1 free dig deep from Bram's encouragement", or "2 free dig deeps" when no giver is known. */
export function digDeepChipLabel(offer: DigDeepOffer): string {
  const count =
    offer.free_dig_deeps === 1 ? '1 free dig deep' : `${offer.free_dig_deeps} free dig deeps`;
  return offer.given_by ? `${count} from ${offer.given_by}'s encouragement` : count;
}
