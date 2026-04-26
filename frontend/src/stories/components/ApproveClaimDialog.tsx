/**
 * ApproveClaimDialog — Lead GM approves a pending AGM claim.
 *
 * Accepts an optional framing note so the Lead GM can set context
 * for the AGM's session before they run it.
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
import { useApproveClaim } from '../queries';
import type { GMQueuePendingClaim } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ApproveClaimDialogProps {
  claim: GMQueuePendingClaim;
}

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  framing_note?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ApproveClaimDialog({ claim }: ApproveClaimDialogProps) {
  const [open, setOpen] = useState(false);
  const [framingNote, setFramingNote] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const approveMutation = useApproveClaim();

  function resetForm() {
    setFramingNote('');
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});

    approveMutation.mutate(
      {
        claimId: claim.claim_id,
        framing_note: framingNote.trim() || undefined,
      },
      {
        onSuccess: () => {
          setOpen(false);
          resetForm();
          toast.success('Claim approved');
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
        <Button variant="default" size="sm">
          Approve
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Approve AGM claim</DialogTitle>
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

            {/* Framing note */}
            <div className="space-y-1.5">
              <Label htmlFor="approve-framing-note">
                Framing note <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="approve-framing-note"
                placeholder="Context for the AGM's session — e.g. 'This scene takes place at the temple at dusk…'"
                value={framingNote}
                onChange={(e) => setFramingNote(e.target.value)}
                rows={4}
              />
              {fieldErrors.framing_note && fieldErrors.framing_note.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.framing_note.join(' ')}</p>
              )}
            </div>
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={approveMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={approveMutation.isPending}>
              {approveMutation.isPending ? 'Approving…' : 'Approve Claim'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
