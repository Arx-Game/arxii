/**
 * ConversionOfferBanner — site-wide alert when the account has a PENDING
 * WorshipConversionOffer (#2361). Mirrors SeanceOfferBanner exactly: mounted
 * globally in Layout, gates on account presence only (not
 * available_characters.length — the same reasoning applies, though a
 * conversion offer always names a live honoree rather than a retired one).
 */

import { useState } from 'react';
import { useConversionOffers } from './queries';
import { ConversionOfferDialog } from './ConversionOfferDialog';

export function ConversionOfferBanner() {
  const { data } = useConversionOffers();
  const [openOfferId, setOpenOfferId] = useState<number | null>(null);
  const offers = data ?? [];

  if (offers.length === 0) {
    return <div data-testid="conversion-offer-banner-empty" hidden />;
  }

  const openOffer = offers.find((o) => o.id === openOfferId) ?? null;

  return (
    <div
      data-testid="conversion-offer-banner"
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
          A conversion to {offer.presented_being_name} is offered to {offer.honoree_name} at{' '}
          {offer.ceremony_location_name}
        </button>
      ))}
      {openOffer && (
        <ConversionOfferDialog
          offer={openOffer}
          open={!!openOffer}
          onOpenChange={(open) => !open && setOpenOfferId(null)}
        />
      )}
    </div>
  );
}
