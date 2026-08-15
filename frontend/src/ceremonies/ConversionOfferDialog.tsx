/**
 * ConversionOfferDialog — accept/decline prompt for a pending public-conversion
 * offer (#2361). Mirrors SeanceOfferDialog's structure/idiom, plus the
 * heart-vs-lip-service choice (Ratified amendment #2) as a Switch: accepting
 * sincerely means converting inwardly too; leaving it off is a public act
 * only — the inward truth stays private either way.
 */

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useRespondToConversionOffer } from './queries';
import type { ConversionOffer } from './types';

interface ConversionOfferDialogProps {
  offer: ConversionOffer;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ConversionOfferDialog({ offer, open, onOpenChange }: ConversionOfferDialogProps) {
  const respond = useRespondToConversionOffer();
  const [sincere, setSincere] = useState(true);

  function handle(accept: boolean) {
    respond.mutate(
      { offerId: offer.id, accept, sincere },
      { onSuccess: () => onOpenChange(false) }
    );
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
          <DialogTitle>A conversion is offered to {offer.presented_being_name}</DialogTitle>
          <DialogDescription>
            {offer.honoree_name} is named to convert to {offer.presented_being_name} at{' '}
            {offer.ceremony_location_name}. Accepting makes the conversion public; declining leaves
            the rite unanswered.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between">
          <Label htmlFor="conversion-offer-sincere">Convert inwardly too</Label>
          <Switch
            id="conversion-offer-sincere"
            checked={sincere}
            onCheckedChange={setSincere}
            data-testid="conversion-offer-sincere-switch"
          />
        </div>

        {respond.isError ? (
          <div
            role="alert"
            data-testid="conversion-offer-respond-error"
            className="rounded-md border border-red-600/60 bg-red-950/40 p-3 text-sm font-medium text-red-200"
          >
            {respond.error?.message || 'Your answer did not land; please try again.'}
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => handle(false)} disabled={respond.isPending}>
            Decline
          </Button>
          <Button
            onClick={() => handle(true)}
            disabled={respond.isPending}
            data-testid="conversion-offer-accept"
          >
            Accept the conversion
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
