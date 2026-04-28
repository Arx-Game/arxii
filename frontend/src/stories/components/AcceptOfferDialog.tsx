/**
 * AcceptOfferDialog — GM accepts a pending story GM offer.
 *
 * Shows a confirmation with an optional response_note textarea.
 * On success, the story is assigned to the GM's first ACTIVE table.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
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
import { useAcceptOffer } from '../queries';
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

interface AcceptOfferDialogProps {
  offer: StoryGMOffer;
  storyTitle?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AcceptOfferDialog({ offer, storyTitle }: AcceptOfferDialogProps) {
  const [open, setOpen] = useState(false);
  const [responseNote, setResponseNote] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const navigate = useNavigate();
  const acceptMutation = useAcceptOffer();

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

    acceptMutation.mutate(
      {
        offerId: offer.id,
        response_note: responseNote.trim() || undefined,
      },
      {
        onSuccess: (updated) => {
          setOpen(false);
          resetForm();
          toast.success(`Story accepted — it is now at your table`, {
            action: {
              label: 'View story',
              onClick: () => void navigate(`/stories/${updated.story}`),
            },
          });
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
              toast.error(err instanceof Error ? err.message : 'Failed to accept offer');
            })
            .catch(() => {
              toast.error('Failed to accept offer. Please try again.');
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
        <Button variant="default" size="sm" data-testid="accept-offer-trigger">
          Accept
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Accept story offer</DialogTitle>
            <DialogDescription>
              Accept &quot;{displayTitle}&quot;? The story will be assigned to your first active
              table.
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
              <Label htmlFor="accept-response-note">
                Response note <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="accept-response-note"
                placeholder="Any message for the player, e.g. 'Welcome to the table! We'll start with…'"
                value={responseNote}
                onChange={(e) => setResponseNote(e.target.value)}
                rows={3}
                data-testid="accept-response-note-input"
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
              disabled={acceptMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={acceptMutation.isPending}
              data-testid="accept-confirm-button"
            >
              {acceptMutation.isPending ? 'Accepting…' : 'Accept Story'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
