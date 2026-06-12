/**
 * AudereMajoraOfferGate — mounts in the combat panel; polls pending Audere
 * Majora crossing offers for the puppeted character, renders a high-prominence
 * amber call-out strip, and auto-opens AudereMajoraOfferDialog once per offer
 * id (re-openable from the strip).
 */

import { DoorOpen } from 'lucide-react';
import { usePendingAudereMajoraOffers, useRespondToAudereMajora } from '@/magic/queries';
import { useAutoOpenOncePerOffer } from '@/magic/hooks';
import { AudereMajoraOfferDialog } from './AudereMajoraOfferDialog';
import type { PendingAudereMajoraOffer } from '@/magic/types';

interface AudereMajoraOfferGateProps {
  characterSheetId: number;
  characterId: number;
  encounterId: number;
}

export function AudereMajoraOfferGate({
  characterSheetId,
  characterId,
  encounterId,
}: AudereMajoraOfferGateProps) {
  // enabled guard: never poll without a resolved character.
  const { data } = usePendingAudereMajoraOffers(characterSheetId > 0);
  const respond = useRespondToAudereMajora(characterId, encounterId);

  const offers = data?.results ?? [];
  const offer: PendingAudereMajoraOffer | null =
    offers.find((o) => o.character_sheet_id === characterSheetId) ?? null;

  // Auto-open once per offer id (max ceremony); dismissing leaves the strip.
  const { dialogOpen, setDialogOpen } = useAutoOpenOncePerOffer(offer);

  if (!offer) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setDialogOpen(true)}
        className="flex w-full animate-pulse items-center gap-2 rounded-md border border-amber-500/60 bg-amber-950/40 px-3 py-2 text-left text-sm font-semibold text-amber-300 shadow-[0_0_24px_-8px] shadow-amber-500/60 motion-reduce:animate-none"
        data-testid="audere-majora-gate-strip"
      >
        <DoorOpen className="h-4 w-4 shrink-0" />
        The threshold stands open — answer it
      </button>
      <AudereMajoraOfferDialog
        offer={offer}
        open={dialogOpen}
        onOpenChange={(next) => {
          setDialogOpen(next);
          if (!next) respond.reset();
        }}
        onAccept={(pathId, declarationText) => {
          respond.mutate(
            {
              offer_id: offer.id,
              accept: true,
              path_id: pathId,
              declaration_text: declarationText,
            },
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
              'The threshold did not answer — your response failed to land. Try again.'
            : null
        }
      />
    </>
  );
}
