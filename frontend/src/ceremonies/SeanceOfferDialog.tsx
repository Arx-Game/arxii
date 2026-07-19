/**
 * SeanceOfferDialog — accept/decline prompt for a pending seance offer
 * (#2393). Mirrors EntryFlourishOfferDialog's structure/idiom.
 */

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useRespondToSeanceOffer } from './queries';
import type { SeanceOffer } from './types';

interface SeanceOfferDialogProps {
  offer: SeanceOffer;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SeanceOfferDialog({ offer, open, onOpenChange }: SeanceOfferDialogProps) {
  const respond = useRespondToSeanceOffer();

  function handle(accept: boolean) {
    respond.mutate({ offerId: offer.id, accept }, { onSuccess: () => onOpenChange(false) });
  }

  function handleOpenChange(next: boolean) {
    if (!next) {
      respond.reset();
    }
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>A seance calls for {offer.honoree_name}</DialogTitle>
          <DialogDescription>
            A rite is underway at {offer.ceremony_location_name}, calling {offer.honoree_name}
            &apos;s voice back for as long as it stays open. Accepting lets you answer; declining
            leaves the rite unanswered.
          </DialogDescription>
        </DialogHeader>

        {respond.isError ? (
          <div
            role="alert"
            data-testid="seance-offer-respond-error"
            className="rounded-md border border-red-600/60 bg-red-950/40 p-3 text-sm font-medium text-red-200"
          >
            {respond.error?.message || 'Your answer did not land — please try again.'}
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => handle(false)} disabled={respond.isPending}>
            Decline
          </Button>
          <Button
            onClick={() => handle(true)}
            disabled={respond.isPending}
            data-testid="seance-offer-accept"
          >
            Answer the call
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
