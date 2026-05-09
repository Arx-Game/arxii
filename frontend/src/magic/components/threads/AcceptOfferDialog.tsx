/**
 * AcceptOfferDialog — confirms acceptance of a ThreadWeavingTeachingOffer.
 *
 * Displays the XP and gold cost, then calls useAcceptTeachingOffer on confirm.
 * Errors are shown inline. On success the dialog closes (the hook already
 * invalidates the teaching-offers list query).
 */
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAcceptTeachingOffer } from '../../queries';
import type { ThreadWeavingTeachingOffer } from '../../types';

interface AcceptOfferDialogProps {
  offer: ThreadWeavingTeachingOffer;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AcceptOfferDialog({ offer, open, onOpenChange }: AcceptOfferDialogProps) {
  const { mutate, isPending, isError, error } = useAcceptTeachingOffer();

  const handleConfirm = () => {
    mutate(
      { offerId: offer.id },
      {
        onSuccess: () => {
          onOpenChange(false);
        },
      }
    );
  };

  const xpCost = offer.effective_xp_cost_for_viewer;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="accept-offer-dialog">
        <DialogHeader>
          <DialogTitle>Accept Teaching Offer?</DialogTitle>
          <DialogDescription data-testid="accept-offer-description">
            You are about to accept the offer to unlock{' '}
            <strong>
              {offer.unlock_target_kind} &mdash; {offer.unlock_display_name}
            </strong>
            .
          </DialogDescription>
        </DialogHeader>

        {/* Cost summary */}
        <div className="space-y-1 text-sm" data-testid="accept-offer-cost-summary">
          {xpCost !== null && (
            <p>
              <span className="font-semibold">{xpCost} XP</span> will be spent from your account.
            </p>
          )}
          {offer.gold_cost > 0 && (
            <p>
              <span className="font-semibold">{offer.gold_cost} Gold</span> will be paid to the
              teacher.
            </p>
          )}
        </div>

        {/* Inline error */}
        {isError && (
          <p className="text-sm text-destructive" role="alert" data-testid="accept-offer-error">
            {error instanceof Error ? error.message : 'Failed to accept offer. Please try again.'}
          </p>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="default"
            onClick={handleConfirm}
            disabled={isPending}
            data-testid="accept-offer-confirm"
          >
            {isPending ? 'Accepting…' : 'Accept Offer'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
