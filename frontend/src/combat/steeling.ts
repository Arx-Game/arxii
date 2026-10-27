/** Helpers for steeling yourself (#4738): the dispatch request and the cost label. */

import type { components } from '@/generated/api';
import type { DispatchActionRequest } from './types';

type SteelOffer = components['schemas']['SteelOffer'];

export const STEEL_REGISTRY_KEY = 'combat_steel';

/** A `combat_steel` registry dispatch. */
export function steelRequest(): DispatchActionRequest {
  return { ref: { backend: 'registry', registry_key: STEEL_REGISTRY_KEY }, kwargs: {} };
}

/** "Free" while a free steel is held, else "Costs mental fatigue 3". */
export function steelCostLabel(offer: SteelOffer): string {
  if (offer.free_steels > 0) return 'Free';
  return `Costs ${offer.fatigue_category} fatigue ${offer.fatigue_cost}`;
}
