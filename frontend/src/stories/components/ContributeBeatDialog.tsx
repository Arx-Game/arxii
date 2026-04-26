/**
 * ContributeBeatDialog — action dialog for AGGREGATE_THRESHOLD beats.
 *
 * Opened from BeatRow when the beat is aggregate and the player has a
 * character_sheet to contribute with.  On success, React Query invalidates
 * the contributions and active-stories caches so the progress bar updates
 * immediately.
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useContributeToBeat } from '../queries';
import type { Beat } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ContributeBeatDialogProps {
  beat: Beat;
  /**
   * The character sheet ID that will be submitted with the contribution.
   * For CHARACTER-scope stories this is story.character_sheet.
   * For GROUP/GLOBAL scope the caller should pass the appropriate sheet id,
   * or omit to let the server produce a validation error.
   */
  characterSheetId: number;
  /** Current contribution total so the max-points hint is accurate. */
  currentTotal: number;
}

// ---------------------------------------------------------------------------
// DRF field-error shape
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  points?: string[];
  source_note?: string[];
  character_sheet?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ContributeBeatDialog({
  beat,
  characterSheetId,
  currentTotal,
}: ContributeBeatDialogProps) {
  const [open, setOpen] = useState(false);
  const [points, setPoints] = useState<string>('1');
  const [sourceNote, setSourceNote] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const contributeMutation = useContributeToBeat();

  const required = beat.required_points ?? 0;
  const remaining = Math.max(0, required - currentTotal);
  const outcome = beat.outcome ?? 'unsatisfied';
  const isResolved = outcome === 'success' || outcome === 'failure' || outcome === 'expired';

  // Visible title for the dialog header
  const beatLabel =
    beat.player_hint && beat.player_hint.trim().length > 0
      ? beat.player_hint
      : beat.visibility === 'secret'
        ? '(Hidden Beat)'
        : 'Beat';

  // Client-side points validation
  const parsedPoints = parseInt(points, 10);
  const pointsInvalid =
    isNaN(parsedPoints) || parsedPoints < 1 || (remaining > 0 && parsedPoints > remaining);

  function resetForm() {
    setPoints('1');
    setSourceNote('');
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      resetForm();
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (pointsInvalid) return;

    setFieldErrors({});

    contributeMutation.mutate(
      {
        beatId: beat.id,
        character_sheet: characterSheetId,
        points: parsedPoints,
        source_note: sourceNote.trim() || undefined,
      },
      {
        onSuccess: () => {
          setOpen(false);
          resetForm();
          toast.success('Contribution recorded');
        },
        onError: (err: unknown) => {
          // Surface DRF validation errors inline
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
          // Fallback for non-DRF errors
          const message =
            err instanceof Error ? err.message : 'An error occurred. Please try again.';
          toast.error(message);
        },
      }
    );
  }

  // Non-field DRF errors banner content
  const nonFieldErrors = fieldErrors.non_field_errors ?? [];
  const detailError = fieldErrors.detail ?? '';

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={isResolved}
          title={isResolved ? 'This beat has already been resolved.' : undefined}
        >
          Contribute
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Contribute to &ldquo;{beatLabel}&rdquo;</DialogTitle>
            <DialogDescription>
              {currentTotal} of {required} points reached
              {remaining > 0 ? ` — ${remaining} still needed` : ' — threshold met'}
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

          {/* Character sheet error (ownership validation) */}
          {fieldErrors.character_sheet && fieldErrors.character_sheet.length > 0 && (
            <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {fieldErrors.character_sheet.map((msg, i) => (
                <p key={i}>{msg}</p>
              ))}
            </div>
          )}

          <div className="mt-4 grid gap-4">
            {/* Points */}
            <div className="space-y-1.5">
              <Label htmlFor="contribute-points">
                Points{remaining > 0 ? ` (max ${remaining})` : ''}
              </Label>
              <Input
                id="contribute-points"
                type="number"
                min={1}
                max={remaining > 0 ? remaining : undefined}
                value={points}
                onChange={(e) => setPoints(e.target.value)}
                required
              />
              {fieldErrors.points && fieldErrors.points.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.points.join(' ')}</p>
              )}
            </div>

            {/* Source note */}
            <div className="space-y-1.5">
              <Label htmlFor="contribute-note">
                Source note <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="contribute-note"
                placeholder="e.g. siege battle, mission completion…"
                value={sourceNote}
                onChange={(e) => setSourceNote(e.target.value)}
                rows={2}
              />
              {fieldErrors.source_note && fieldErrors.source_note.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.source_note.join(' ')}</p>
              )}
            </div>
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={contributeMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={contributeMutation.isPending || pointsInvalid}>
              {contributeMutation.isPending ? 'Submitting…' : 'Submit Contribution'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
