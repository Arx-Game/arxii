/**
 * AudereOfferDialog — the single most dramatic prompt in combat (#873).
 *
 * Renders the Audere offer with full ceremony: the gate's stakes from
 * AudereThreshold, and — when present — the corruption advisory VERBATIM in a
 * role="alert" block (risk-is-always-explicit; the "character loss" sentence
 * must reach the player unedited).
 */

import { Flame } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import type { PendingAudereOffer } from '@/magic/types';

interface AudereOfferDialogProps {
  offer: PendingAudereOffer;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAccept: () => void;
  onDecline: () => void;
  isPending: boolean;
}

export function AudereOfferDialog({
  offer,
  open,
  onOpenChange,
  onAccept,
  onDecline,
  isPending,
}: AudereOfferDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="border-fuchsia-500/60 shadow-[0_0_60px_-12px] shadow-fuchsia-500/50">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-2xl font-bold tracking-wide text-fuchsia-400">
            <Flame className="h-7 w-7" />
            The Audere Gate Stands Open
          </AlertDialogTitle>
          <AlertDialogDescription className="text-base">
            Battered down. Break through. Your soul strains at intensity{' '}
            <span className="font-semibold text-fuchsia-400">{offer.fired_intensity}</span> — power
            beyond your limits waits on the other side.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="grid grid-cols-2 gap-3 rounded-md border border-fuchsia-500/30 bg-fuchsia-950/20 p-3 text-sm">
          <div>
            <span className="font-semibold text-fuchsia-300">+{offer.intensity_bonus}</span>{' '}
            Intensity
          </div>
          <div>
            <span className="font-semibold text-fuchsia-300">+{offer.anima_pool_bonus}</span> Anima
            maximum
          </div>
        </div>

        {offer.advisory_text ? (
          <div
            role="alert"
            className="rounded-md border border-red-600/60 bg-red-950/40 p-3 text-sm font-medium text-red-200"
          >
            {offer.advisory_text}
          </div>
        ) : null}

        <AlertDialogFooter>
          <Button variant="outline" onClick={onDecline} disabled={isPending}>
            Hold Fast
          </Button>
          <Button
            className="bg-fuchsia-600 text-white hover:bg-fuchsia-500"
            onClick={onAccept}
            disabled={isPending}
          >
            <Flame className="mr-1.5 h-4 w-4" />
            Break Through
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
