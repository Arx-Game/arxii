/**
 * RequestClaimDialog — AGM submits a claim request on an AGM-eligible beat.
 *
 * Wave 7: AGM-perspective claim flow.
 *
 * The dialog accepts an optional framing note — the AGM's pitch / how they'd
 * handle the scene — which the Lead GM sees when deciding to approve or reject.
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
import { useRequestClaim } from '../queries';
import type { Beat } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RequestClaimDialogProps {
  beat: Beat;
}

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  beat?: string[];
  framing_note?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RequestClaimDialog({ beat }: RequestClaimDialogProps) {
  const [open, setOpen] = useState(false);
  const [framingNote, setFramingNote] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const requestMutation = useRequestClaim();

  const beatLabel =
    beat.player_hint && beat.player_hint.trim().length > 0
      ? beat.player_hint
      : (beat.internal_description ?? 'Beat');

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

    requestMutation.mutate(
      {
        beat: beat.id,
        framing_note: framingNote.trim() || undefined,
      },
      {
        onSuccess: () => {
          setOpen(false);
          resetForm();
          toast.success('Claim submitted');
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
  const beatErrors = fieldErrors.beat ?? [];

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="default" size="sm">
          Request Claim
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Request claim on beat</DialogTitle>
            <DialogDescription className="line-clamp-3">{beatLabel}</DialogDescription>
          </DialogHeader>

          {/* Non-field / global error banner */}
          {(nonFieldErrors.length > 0 || detailError || beatErrors.length > 0) && (
            <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {detailError && <p>{detailError}</p>}
              {nonFieldErrors.map((msg, i) => (
                <p key={i}>{msg}</p>
              ))}
              {beatErrors.map((msg, i) => (
                <p key={i}>{msg}</p>
              ))}
            </div>
          )}

          <div className="mt-4 grid gap-4">
            {/* Beat context block */}
            {beat.story_title && (
              <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
                <p>
                  <span className="font-medium">Story: </span>
                  {beat.story_title}
                </p>
                {beat.chapter_title && (
                  <p>
                    <span className="font-medium">Chapter: </span>
                    {beat.chapter_title}
                  </p>
                )}
                {beat.episode_title && (
                  <p>
                    <span className="font-medium">Episode: </span>
                    {beat.episode_title}
                  </p>
                )}
              </div>
            )}

            {/* Framing note */}
            <div className="space-y-1.5">
              <Label htmlFor="request-framing-note">
                Framing note <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="request-framing-note"
                placeholder="Your pitch — how you'd handle this scene, what tone you'd bring, any relevant character knowledge…"
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
              disabled={requestMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={requestMutation.isPending}>
              {requestMutation.isPending ? 'Submitting…' : 'Submit Claim'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
