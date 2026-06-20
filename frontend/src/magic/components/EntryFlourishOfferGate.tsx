/**
 * EntryFlourishOfferGate — mounts in the scene panel; polls pending entry-
 * flourish offers for the active character, renders a call-out strip, and
 * auto-opens EntryFlourishOfferDialog once per offer id (re-openable from
 * the strip). Mirrors AudereOfferGate's structure.
 */

import { Sparkles } from 'lucide-react';
import { usePendingEntryFlourishOffers } from '@/magic/queries';
import { useAutoOpenOncePerOffer } from '@/magic/hooks';
import { EntryFlourishOfferDialog } from './EntryFlourishOfferDialog';
import type { PendingEntryFlourishOffer } from '@/magic/types';

interface EntryFlourishOfferGateProps {
  characterSheetId: number;
}

export function EntryFlourishOfferGate({ characterSheetId }: EntryFlourishOfferGateProps) {
  // enabled guard: never poll without a resolved character.
  const { data } = usePendingEntryFlourishOffers(characterSheetId > 0);

  const offers = data?.results ?? [];
  const offer: PendingEntryFlourishOffer | null =
    offers.find((o) => o.character_sheet_id === characterSheetId) ?? null;

  // Auto-open once per offer id (max ceremony); dismissing leaves the strip.
  const { dialogOpen, setDialogOpen } = useAutoOpenOncePerOffer(offer);

  if (!offer) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setDialogOpen(true)}
        className="flex w-full animate-pulse items-center gap-2 rounded-md border border-emerald-500/60 bg-emerald-950/40 px-3 py-2 text-left text-sm font-semibold text-emerald-300 shadow-[0_0_24px_-8px] shadow-emerald-500/60 motion-reduce:animate-none"
        data-testid="entry-flourish-gate-strip"
      >
        <Sparkles className="h-4 w-4 shrink-0" />
        Declare your resonance as you enter the scene
      </button>
      <EntryFlourishOfferDialog
        offer={offer}
        characterSheetId={characterSheetId}
        open={dialogOpen}
        onOpenChange={(next) => setDialogOpen(next)}
        onClose={() => setDialogOpen(false)}
      />
    </>
  );
}
