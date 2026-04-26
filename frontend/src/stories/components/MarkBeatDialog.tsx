/**
 * MarkBeatDialog — GM action to mark the outcome of a GM_MARKED beat.
 *
 * Opened from BeatRow for GM_MARKED beats.  The "Mark" button is rendered
 * optimistically — the API 403 surfaces as an error toast if the user
 * does not have permission (Lead GM, staff, or AGM with approved claim).
 *
 * Decision: a future wave could add a `can_mark` boolean to the Beat
 * serializer for cleaner UX (hide the button for unauthorised users), but
 * this requires a backend change and is deferred.
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
import { useMarkBeat } from '../queries';
import type { Beat, BeatOutcome } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface MarkBeatDialogProps {
  beat: Beat;
}

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  outcome?: string[];
  gm_notes?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const OUTCOMES: { value: BeatOutcome; label: string }[] = [
  { value: 'success', label: 'Success' },
  { value: 'failure', label: 'Failure' },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MarkBeatDialog({ beat }: MarkBeatDialogProps) {
  const [open, setOpen] = useState(false);
  const [outcome, setOutcome] = useState<BeatOutcome>('success');
  const [gmNotes, setGmNotes] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const markMutation = useMarkBeat();

  const beatLabel =
    beat.player_hint && beat.player_hint.trim().length > 0
      ? beat.player_hint
      : (beat.internal_description ?? 'Beat');

  function resetForm() {
    setOutcome('success');
    setGmNotes('');
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});

    markMutation.mutate(
      {
        beatId: beat.id,
        outcome,
        gm_notes: gmNotes.trim() || undefined,
      },
      {
        onSuccess: () => {
          setOpen(false);
          resetForm();
          toast.success('Beat marked');
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
        <Button variant="outline" size="sm">
          Mark
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Mark beat: &ldquo;{beatLabel}&rdquo;</DialogTitle>
            <DialogDescription>Record the outcome of this GM-marked beat.</DialogDescription>
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
            {/* Outcome radio */}
            <div className="space-y-2">
              <Label>Outcome</Label>
              <div className="space-y-2">
                {OUTCOMES.map((o) => (
                  <label
                    key={o.value}
                    className="flex cursor-pointer items-center gap-3 rounded-md border p-3 hover:bg-accent"
                  >
                    <input
                      type="radio"
                      name="outcome"
                      value={o.value}
                      checked={outcome === o.value}
                      onChange={() => setOutcome(o.value)}
                      className="h-4 w-4"
                    />
                    <span className="text-sm font-medium">{o.label}</span>
                  </label>
                ))}
              </div>
              {fieldErrors.outcome && fieldErrors.outcome.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.outcome.join(' ')}</p>
              )}
            </div>

            {/* GM notes */}
            <div className="space-y-1.5">
              <Label htmlFor="mark-beat-gm-notes">
                GM notes <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="mark-beat-gm-notes"
                placeholder="Notes for the story record…"
                value={gmNotes}
                onChange={(e) => setGmNotes(e.target.value)}
                rows={3}
              />
              {fieldErrors.gm_notes && fieldErrors.gm_notes.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.gm_notes.join(' ')}</p>
              )}
            </div>
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={markMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={markMutation.isPending}>
              {markMutation.isPending ? 'Marking…' : 'Mark Beat'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
