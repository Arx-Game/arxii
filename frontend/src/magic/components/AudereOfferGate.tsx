/**
 * AudereOfferGate — mounts in the combat panel; polls pending Audere offers for
 * the puppeted character, renders a high-prominence call-out strip, and
 * auto-opens AudereOfferDialog once per offer id (re-openable from the strip).
 */

import { useEffect, useState } from 'react';
import { Flame } from 'lucide-react';
import { usePendingAudereOffers, useRespondToAudere } from '@/magic/queries';
import { AudereOfferDialog } from './AudereOfferDialog';
import type { PendingAudereOffer } from '@/magic/types';

interface AudereOfferGateProps {
  characterSheetId: number;
  characterId: number;
  encounterId: number;
}

export function AudereOfferGate({
  characterSheetId,
  characterId,
  encounterId,
}: AudereOfferGateProps) {
  // enabled guard: never poll without a resolved character (Task 7 review).
  const { data } = usePendingAudereOffers(characterSheetId > 0);
  const respond = useRespondToAudere(characterId, encounterId);

  const offers = data?.results ?? [];
  const offer: PendingAudereOffer | null =
    offers.find((o) => o.character_sheet_id === characterSheetId) ?? null;

  const [dialogOpen, setDialogOpen] = useState(false);
  const [seenOfferId, setSeenOfferId] = useState<number | null>(null);

  // Auto-open once per offer id (max ceremony); dismissing leaves the strip.
  useEffect(() => {
    if (offer && offer.id !== seenOfferId) {
      setSeenOfferId(offer.id);
      setDialogOpen(true);
    }
  }, [offer, seenOfferId]);

  if (!offer) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setDialogOpen(true)}
        className="flex w-full animate-pulse items-center gap-2 rounded-md border border-fuchsia-500/60 bg-fuchsia-950/40 px-3 py-2 text-left text-sm font-semibold text-fuchsia-300 shadow-[0_0_24px_-8px] shadow-fuchsia-500/60 motion-reduce:animate-none"
        data-testid="audere-gate-strip"
      >
        <Flame className="h-4 w-4 shrink-0" />
        The Audere gate stands open — answer it
      </button>
      <AudereOfferDialog
        offer={offer}
        open={dialogOpen}
        onOpenChange={(next) => {
          setDialogOpen(next);
          if (!next) respond.reset();
        }}
        onAccept={() => {
          respond.mutate(
            { offer_id: offer.id, accept: true },
            { onSuccess: () => setDialogOpen(false) }
          );
        }}
        onDecline={() => {
          respond.mutate(
            { offer_id: offer.id, accept: false },
            { onSuccess: () => setDialogOpen(false) }
          );
        }}
        isPending={respond.isPending}
        errorMessage={
          respond.isError
            ? respond.error?.message ||
              'The gate did not answer — your response failed to land. Try again.'
            : null
        }
      />
    </>
  );
}
