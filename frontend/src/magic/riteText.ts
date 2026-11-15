/** Words for the rite of settling (#5124): how an offering counts, and the open chance to atone. */

import type { DriftConversionOffer, RiteOffering } from '@/magic/types';

/** The item, then how it counts: tied to the resonance, bearing its facet, or a keepsake of it. */
export function offeringLabel(offering: RiteOffering): string {
  const how: Record<string, string> = {
    keepsake: `a keepsake of ${offering.resonance_name}`,
    facet: `bears a facet of ${offering.resonance_name}`,
  };
  return `${offering.name} · ${how[offering.mode] ?? `tied to ${offering.resonance_name}`}`;
}

/** "A chance to atone is open: up to 3 toward Fury." (one clause per resonance it caps). */
export function atoneChanceLine(offer: DriftConversionOffer | undefined): string {
  const clauses =
    offer?.caps
      .filter((cap) => cap.cap_remaining > 0)
      .map((cap) => `up to ${cap.cap_remaining} toward ${cap.target_resonance.name}`) ?? [];
  return clauses.length > 0 ? `A chance to atone is open: ${clauses.join(', ')}.` : '';
}
