/**
 * DeclineOfferDialog — GM declines a pending story GM offer.
 *
 * Shows a confirmation with an optional response_note textarea.
 * On success the story remains in "seeking GM" state.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useDeclineOffer } from '../queries';
import type { StoryGMOffer } from '../types';

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  response_note?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface DeclineOfferDialogProps {
  offer: StoryGMOffer;
  storyTitle?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function DeclineOfferDialog({ offer, storyTitle }: DeclineOfferDialogProps) {
  const [open, setOpen] = useState(false);
  const [responseNote, setResponseNote] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const declineMutation = useDeclineOffer();

  function resetForm() {
    setResponseNote('');
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});

    declineMutation.mutate(
      {
        offerId: offer.id,
        response_note: responseNote.trim() || undefined,
      },
      {
        onSuccess: () => {
          setOpen(false);
          resetForm();
          toast.success('Offer declined');
        },
        onError: (err: unknown) => {
          void Promise.resolve()
            .then(async () => {
              const fetchErr = err as { response?: Response };
              if (fetchErr.response) {
                const data: unknown = await fetchErr.response.json();
                if (data && typeof data === 'object') {
                  setFieldErrors(data as DRFFieldErrors);
                  return;
                }
              }
              toast.error(err instanceof Error ? err.message : 'Failed to decline offer');
            })
            .catch(() => {
              toast.error('Failed to decline offer. Please try again.');
            });
        },
      }
    );
  }

  const displayTitle = storyTitle ?? `Story #${offer.story}`;
  const nonFieldErrors = fieldErrors.non_field_errors ?? [];
  const detailError = fieldErrors.detail ?? '';

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" data-testid="decline-offer-trigger">
          Decline
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Decline story offer</DialogTitle>
            <DialogDescription>
              Decline &quot;{displayTitle}&quot;? The story will remain in &quot;seeking GM&quot;
              state.
            </DialogDescription>
          </DialogHeader>

          {/* Global error banner */}
          {(nonFieldErrors.length > 0 || detailError) && (
            <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {detailError && <p>{detailError}</p>}
              {nonFieldErrors.map((msg, i) => (
                <p key={i}>{msg}</p>
              ))}
            </div>
          )}

          <div className="mt-4 grid gap-4">
            {/* Player message preview */}
            {offer.message && (
              <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
                <span className="font-medium">Player message: </span>
                {offer.message}
              </div>
            )}

            {/* Optional response note */}
            <div className="space-y-1.5">
              <Label htmlFor="decline-response-note">
                Response note <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="decline-response-note"
                placeholder="Optional note for the player, e.g. 'I'm at capacity right now…'"
                value={responseNote}
                onChange={(e) => setResponseNote(e.target.value)}
                rows={3}
                data-testid="decline-response-note-input"
              />
              {fieldErrors.response_note && fieldErrors.response_note.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.response_note.join(' ')}</p>
              )}
            </div>
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={declineMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={declineMutation.isPending}
              data-testid="decline-confirm-button"
            >
              {declineMutation.isPending ? 'Declining…' : 'Decline Offer'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
