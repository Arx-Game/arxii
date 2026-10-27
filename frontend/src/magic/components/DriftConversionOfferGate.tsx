/**
 * DriftConversionOfferGate (#4733) - polls the account's open drift conversion
 * offers, renders a call-out strip, and auto-opens DriftConversionOfferDialog
 * once per offer id (re-openable from the strip). Mirrors EntryFlourishOfferGate.
 *
 * Mounted on every surface a live player sits on (the scene page and the game
 * page), once per surface. The inbox is account-scoped and carries no character
 * id, so the gate shows the first open offer.
 *
 * An exhausted offer leaves the inbox the moment the rite finishes, so the gate
 * keeps the result line the dialog hands back until the player closes it.
 */

import { useState } from 'react';
import { Flame } from 'lucide-react';
import { usePendingDriftConversionOffers } from '@/magic/queries';
import { useAutoOpenOncePerOffer } from '@/magic/hooks';
import { DriftConversionOfferDialog } from './DriftConversionOfferDialog';

export function DriftConversionOfferGate() {
  const { data } = usePendingDriftConversionOffers();
  const [resultLine, setResultLine] = useState<string | null>(null);

  const offer = data?.results?.[0] ?? null;

  const { dialogOpen, setDialogOpen } = useAutoOpenOncePerOffer(offer?.id ?? null);

  function handleClose() {
    setDialogOpen(false);
    setResultLine(null);
  }

  if (!offer && !resultLine) return null;

  return (
    <>
      {offer ? (
        <button
          type="button"
          onClick={() => setDialogOpen(true)}
          className="flex w-full animate-pulse items-center gap-2 rounded-md border border-amber-500/60 bg-amber-950/40 px-3 py-2 text-left text-sm font-semibold text-amber-300 shadow-[0_0_24px_-8px] shadow-amber-500/60 motion-reduce:animate-none"
          data-testid="drift-conversion-gate-strip"
        >
          <Flame className="h-4 w-4 shrink-0" />
          Conversion offer
        </button>
      ) : null}
      <DriftConversionOfferDialog
        offer={offer}
        resultLine={resultLine}
        onResult={setResultLine}
        open={dialogOpen || (!offer && resultLine !== null)}
        onOpenChange={(next) => (next ? setDialogOpen(true) : handleClose())}
        onClose={handleClose}
      />
    </>
  );
}
