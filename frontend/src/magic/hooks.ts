/**
 * Shared hooks for the magic module.
 */

import { useEffect, useState } from 'react';

/**
 * Auto-open a dialog exactly once per key, then allow re-open from the strip.
 *
 * Shared by AudereOfferGate, AudereMajoraOfferGate, and UltimateRevealGate
 * (#4098): all three carry the same "show dialog on first sight of a new
 * key; dismiss leaves the strip open" ceremony pattern. The key is whatever
 * uniquely identifies "a new thing worth re-prompting for" — an offer id for
 * the ceremony gates, a reveal's joined choice_keys for the ultimate gate.
 *
 * @param key - The current key (null when nothing is pending).
 * @returns `{ dialogOpen, setDialogOpen }` — bind to the dialog's open state.
 */
export function useAutoOpenOncePerOffer(key: string | number | null): {
  dialogOpen: boolean;
  setDialogOpen: (open: boolean) => void;
} {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [seenKey, setSeenKey] = useState<string | number | null>(null);

  useEffect(() => {
    if (key !== null && key !== seenKey) {
      setSeenKey(key);
      setDialogOpen(true);
    }
  }, [key, seenKey]);

  return { dialogOpen, setDialogOpen };
}
