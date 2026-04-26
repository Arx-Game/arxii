/**
 * ResolveEpisodeDialog — GM action to resolve the current episode and advance the story.
 *
 * Opened from EpisodeReadyCard in GMQueuePage.  The eligible_transitions data
 * comes from the GM queue row — no extra fetch needed.
 *
 * Decision: StoryDetailPage Resolve CTA is deferred to a later wave because we
 * don't have a clean GM-detection signal there yet (Wave 11 routing adds it).
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
import { useResolveEpisode } from '../queries';
import type { GMQueueEpisodeEntry } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ResolveEpisodeDialogProps {
  entry: GMQueueEpisodeEntry;
}

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  chosen_transition?: string[];
  gm_notes?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Transition label helpers
// ---------------------------------------------------------------------------

function transitionLabel(t: GMQueueEpisodeEntry['eligible_transitions'][number]): string {
  return t.mode === 'AUTO' ? `Auto transition (mode: AUTO)` : `GM Choice (mode: GM_CHOICE)`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ResolveEpisodeDialog({ entry }: ResolveEpisodeDialogProps) {
  const [open, setOpen] = useState(false);
  const [selectedTransition, setSelectedTransition] = useState<number | null>(() => {
    // Pre-select if exactly one AUTO transition
    if (entry.eligible_transitions.length === 1 && entry.eligible_transitions[0].mode === 'AUTO') {
      return entry.eligible_transitions[0].transition_id;
    }
    return null;
  });
  const [gmNotes, setGmNotes] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const resolveMutation = useResolveEpisode();

  function resetForm() {
    setSelectedTransition(() => {
      if (
        entry.eligible_transitions.length === 1 &&
        entry.eligible_transitions[0].mode === 'AUTO'
      ) {
        return entry.eligible_transitions[0].transition_id;
      }
      return null;
    });
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

    resolveMutation.mutate(
      {
        episodeId: entry.episode_id,
        chosen_transition: selectedTransition ?? undefined,
        gm_notes: gmNotes.trim() || undefined,
      },
      {
        onSuccess: () => {
          setOpen(false);
          resetForm();
          toast.success('Episode resolved');
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
  const hasTransitions = entry.eligible_transitions.length > 0;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="default" size="sm">
          Resolve
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Resolve Episode: {entry.episode_title}</DialogTitle>
            <DialogDescription>{entry.story_title}</DialogDescription>
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
            {/* Eligible transitions */}
            <div className="space-y-2">
              <Label>Transition</Label>
              {!hasTransitions ? (
                <p className="text-sm text-muted-foreground">
                  No eligible transitions — advance to frontier.
                </p>
              ) : (
                <div className="space-y-2">
                  {entry.eligible_transitions.map((t) => (
                    <label
                      key={t.transition_id}
                      className="flex cursor-pointer items-center gap-3 rounded-md border p-3 hover:bg-accent"
                    >
                      <input
                        type="radio"
                        name="transition"
                        value={t.transition_id}
                        checked={selectedTransition === t.transition_id}
                        onChange={() => setSelectedTransition(t.transition_id)}
                        className="h-4 w-4"
                      />
                      <span className="text-sm">{transitionLabel(t)}</span>
                    </label>
                  ))}
                  <label className="flex cursor-pointer items-center gap-3 rounded-md border p-3 hover:bg-accent">
                    <input
                      type="radio"
                      name="transition"
                      value="none"
                      checked={selectedTransition === null}
                      onChange={() => setSelectedTransition(null)}
                      className="h-4 w-4"
                    />
                    <span className="text-sm text-muted-foreground">
                      Advance to frontier — no next episode selected
                    </span>
                  </label>
                </div>
              )}
              {fieldErrors.chosen_transition && fieldErrors.chosen_transition.length > 0 && (
                <p className="text-xs text-destructive">
                  {fieldErrors.chosen_transition.join(' ')}
                </p>
              )}
            </div>

            {/* GM notes */}
            <div className="space-y-1.5">
              <Label htmlFor="resolve-gm-notes">
                GM notes <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="resolve-gm-notes"
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
              disabled={resolveMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={resolveMutation.isPending}>
              {resolveMutation.isPending ? 'Resolving…' : 'Resolve Episode'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
