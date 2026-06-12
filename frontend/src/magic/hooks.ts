/**
 * Shared hooks for the magic module.
 */

import { useEffect, useState } from 'react';

/**
 * Auto-open a dialog exactly once per offer id, then allow re-open from the strip.
 *
 * Shared by AudereOfferGate and AudereMajoraOfferGate: both carry the same
 * "show dialog on first sight of a new offer; dismiss leaves the strip open"
 * ceremony pattern.
 *
 * @param offer - The current pending offer (null when none is present).
 * @returns `{ dialogOpen, setDialogOpen }` — bind to the dialog's open state.
 */
export function useAutoOpenOncePerOffer(offer: { id: number } | null): {
  dialogOpen: boolean;
  setDialogOpen: (open: boolean) => void;
} {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [seenOfferId, setSeenOfferId] = useState<number | null>(null);

  useEffect(() => {
    if (offer && offer.id !== seenOfferId) {
      setSeenOfferId(offer.id);
      setDialogOpen(true);
    }
  }, [offer, seenOfferId]);

  return { dialogOpen, setDialogOpen };
}
