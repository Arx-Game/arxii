/**
 * The feed's "Settle your aura" button asks the composer to open the rite (#5124).
 *
 * The button lives on a feed note and the dialog lives with the composer, which holds the
 * character's sheet id. A DOM event carries the request between them so neither imports the
 * other; the composer listens for as long as it is mounted.
 */

import { useEffect } from 'react';

const SETTLE_AURA_EVENT = 'arx:settle-aura';

export function requestSettleAura(): void {
  window.dispatchEvent(new Event(SETTLE_AURA_EVENT));
}

/** Calls `onRequest` whenever any feed note asks to settle the aura. */
export function useSettleAuraRequests(onRequest: () => void): void {
  useEffect(() => {
    window.addEventListener(SETTLE_AURA_EVENT, onRequest);
    return () => window.removeEventListener(SETTLE_AURA_EVENT, onRequest);
  }, [onRequest]);
}
