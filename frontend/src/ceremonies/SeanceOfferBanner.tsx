/**
 * SeanceOfferBanner — site-wide alert when the account has a PENDING
 * SeanceManifestationOffer (#2393). Mounted globally in Layout (not scene-
 * or character-scoped) because a retired-only honoree's account may have
 * zero available_characters — exactly who most needs to see this. Gates on
 * account presence only (see useSeanceOffers), unlike usePendingAlterations'
 * hasCharacters gate.
 */

import { useState } from 'react';
import { useSeanceOffers } from './queries';
import { SeanceOfferDialog } from './SeanceOfferDialog';

export function SeanceOfferBanner() {
  const { data } = useSeanceOffers();
  const [openOfferId, setOpenOfferId] = useState<number | null>(null);
  const offers = data ?? [];

  if (offers.length === 0) {
    return <div data-testid="seance-offer-banner-empty" hidden />;
  }

  const openOffer = offers.find((o) => o.id === openOfferId) ?? null;

  return (
    <div
      data-testid="seance-offer-banner"
      role="alert"
      className="border-b border-amber-500/40 bg-amber-950/30 px-4 py-2 text-center text-sm text-amber-200"
    >
      {offers.map((offer) => (
        <button
          key={offer.id}
          type="button"
          onClick={() => setOpenOfferId(offer.id)}
          className="mx-2 font-semibold underline underline-offset-2"
        >
          A seance calls for {offer.honoree_name} at {offer.ceremony_location_name}
        </button>
      ))}
      {openOffer && (
        <SeanceOfferDialog
          offer={openOffer}
          open={!!openOffer}
          onOpenChange={(open) => !open && setOpenOfferId(null)}
        />
      )}
    </div>
  );
}
