/**
 * RejectClaimDialog — Lead GM rejects a pending AGM claim.
 *
 * Accepts an optional rejection note to communicate the reason to the AGM.
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
import { useRejectClaim } from '../queries';
import type { GMQueuePendingClaim } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RejectClaimDialogProps {
  claim: GMQueuePendingClaim;
}

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  note?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RejectClaimDialog({ claim }: RejectClaimDialogProps) {
  const [open, setOpen] = useState(false);
  const [rejectionNote, setRejectionNote] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const rejectMutation = useRejectClaim();

  function resetForm() {
    setRejectionNote('');
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});

    rejectMutation.mutate(
      {
        claimId: claim.claim_id,
        note: rejectionNote.trim() || undefined,
      },
      {
        onSuccess: () => {
          setOpen(false);
          resetForm();
          toast.success('Claim rejected');
        },
        onError: (err: unknown) => {
          if (err && typeof err === 'object' && 'response' in err) {
            const response = (err as { response?: Response }).response;
            if (response) {
              void response
                .json()
                .then((data: unknown) => {
                  if (data && typeof data === 'object') {
                    setFieldErrors(data as DRFFieldErrors);
                  }
                })
                .catch(() => {
                  toast.error('An error occurred. Please try again.');
                });
              return;
            }
          }
          const message =
            err instanceof Error ? err.message : 'An error occurred. Please try again.';
          toast.error(message);
        },
      }
    );
  }

  const nonFieldErrors = fieldErrors.non_field_errors ?? [];
  const detailError = fieldErrors.detail ?? '';

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="destructive" size="sm">
          Reject
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Reject AGM claim</DialogTitle>
            <DialogDescription>
              AGM #{claim.assistant_gm_id} — {claim.story_title}
            </DialogDescription>
          </DialogHeader>

          {/* Non-field / global error banner */}
          {(nonFieldErrors.length > 0 || detailError) && (
            <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {detailError && <p>{detailError}</p>}
              {nonFieldErrors.map((msg, i) => (
                <p key={i}>{msg}</p>
              ))}
            </div>
          )}

          <div className="mt-4 grid gap-4">
            {/* Beat description context */}
            {claim.beat_internal_description && (
              <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
                <span className="font-medium">Beat: </span>
                {claim.beat_internal_description}
              </div>
            )}

            {/* Rejection note */}
            <div className="space-y-1.5">
              <Label htmlFor="reject-note">
                Rejection note <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="reject-note"
                placeholder="Reason for rejection…"
                value={rejectionNote}
                onChange={(e) => setRejectionNote(e.target.value)}
                rows={3}
              />
              {fieldErrors.note && fieldErrors.note.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.note.join(' ')}</p>
              )}
            </div>
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={rejectMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" variant="destructive" disabled={rejectMutation.isPending}>
              {rejectMutation.isPending ? 'Rejecting…' : 'Reject Claim'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
