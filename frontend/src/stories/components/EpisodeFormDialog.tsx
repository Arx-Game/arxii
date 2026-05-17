/**
 * EpisodeFormDialog — create or edit an Episode within a Chapter.
 *
 * Fields: title, description (internal GM), summary ("The Story So Far",
 * player-facing), resting_conclusion (player-facing), is_ending, order.
 * On edit, the current maturity is shown read-only (promotion is a separate
 * control). Also embeds ProgressionRequirementsEditor for existing episodes
 * (Task 9.4).
 */

import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useCreateEpisode, useUpdateEpisode } from '../queries';
import type { Episode, Maturity } from '../types';
import { ProgressionRequirementsEditor } from './ProgressionRequirementsEditor';
import { PromoteMaturityButton } from './PromoteMaturityButton';

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  title?: string[];
  description?: string[];
  summary?: string[];
  resting_conclusion?: string[];
  is_ending?: string[];
  order?: string[];
  chapter?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

/** Minimum fields needed from an episode object for the edit form. */
export interface EpisodeLike {
  id: number;
  title: string;
  description?: string;
  summary?: string;
  resting_conclusion?: string;
  is_ending?: boolean;
  maturity?: Maturity;
  order: number;
}

interface EpisodeFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chapterId: number;
  /** When provided, dialog operates in edit mode. */
  episode?: EpisodeLike;
  /**
   * Owning story id. When provided (edit mode), enables the maturity
   * promotion control beside the read-only maturity indicator.
   */
  storyId?: number;
  onSuccess?: (episode: Episode) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function EpisodeFormDialog({
  open,
  onOpenChange,
  chapterId,
  episode,
  storyId,
  onSuccess,
}: EpisodeFormDialogProps) {
  const isEdit = episode !== undefined;

  const [title, setTitle] = useState(episode?.title ?? '');
  const [description, setDescription] = useState(episode?.description ?? '');
  const [summary, setSummary] = useState(episode?.summary ?? '');
  const [restingConclusion, setRestingConclusion] = useState(episode?.resting_conclusion ?? '');
  const [isEnding, setIsEnding] = useState<boolean>(episode?.is_ending ?? false);
  const [order, setOrder] = useState<string>(
    episode?.order !== undefined ? String(episode.order) : ''
  );
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const createMutation = useCreateEpisode();
  const updateMutation = useUpdateEpisode();
  const isPending = createMutation.isPending || updateMutation.isPending;

  function resetForm() {
    setTitle(episode?.title ?? '');
    setDescription(episode?.description ?? '');
    setSummary(episode?.summary ?? '');
    setRestingConclusion(episode?.resting_conclusion ?? '');
    setIsEnding(episode?.is_ending ?? false);
    setOrder(episode?.order !== undefined ? String(episode.order) : '');
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    if (!next) resetForm();
    onOpenChange(next);
  }

  function handleError(err: unknown) {
    if (err && typeof err === 'object' && 'response' in err) {
      const response = (err as { response?: Response }).response;
      if (response) {
        void response
          .json()
          .then((data: unknown) => {
            if (data && typeof data === 'object') setFieldErrors(data as DRFFieldErrors);
          })
          .catch(() => toast.error('An error occurred. Please try again.'));
        return;
      }
    }
    toast.error(err instanceof Error ? err.message : 'An error occurred. Please try again.');
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});

    const data = {
      chapter: chapterId,
      title: title.trim(),
      description: description.trim() || undefined,
      summary: summary.trim() || undefined,
      resting_conclusion: restingConclusion.trim() || undefined,
      is_ending: isEnding,
      order: order !== '' ? Number(order) : undefined,
    };

    if (isEdit && episode) {
      updateMutation.mutate(
        { id: episode.id, data },
        {
          onSuccess: (updated) => {
            toast.success('Episode updated');
            handleOpenChange(false);
            onSuccess?.(updated);
          },
          onError: handleError,
        }
      );
    } else {
      createMutation.mutate(data, {
        onSuccess: (created) => {
          toast.success('Episode created');
          handleOpenChange(false);
          onSuccess?.(created);
        },
        onError: handleError,
      });
    }
  }

  const nonFieldErrors = fieldErrors.non_field_errors ?? [];
  const detailError = fieldErrors.detail ?? '';

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{isEdit ? 'Edit Episode' : 'Create Episode'}</DialogTitle>
          </DialogHeader>

          {(nonFieldErrors.length > 0 || detailError) && (
            <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {detailError && <p>{detailError}</p>}
              {nonFieldErrors.map((msg, i) => (
                <p key={i}>{msg}</p>
              ))}
            </div>
          )}

          <div className="mt-4 grid gap-4">
            {/* Title */}
            <div className="space-y-1.5">
              <Label htmlFor="episode-title">
                Title <span className="text-destructive">*</span>
              </Label>
              <Input
                id="episode-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Episode title"
                required
              />
              {fieldErrors.title && (
                <p className="text-xs text-destructive">{fieldErrors.title.join(' ')}</p>
              )}
            </div>

            {/* Maturity (read-only, edit mode only) + promotion control (Task E3) */}
            {isEdit && episode?.maturity && (
              <div className="flex flex-wrap items-center gap-2">
                <div
                  data-testid="episode-maturity-indicator"
                  className="inline-flex w-fit items-center rounded-md border bg-muted px-2 py-1 text-xs text-muted-foreground"
                >
                  Maturity: <span className="ml-1 font-medium capitalize">{episode.maturity}</span>
                </div>
                {storyId !== undefined && (
                  <PromoteMaturityButton
                    episode={{ id: episode.id, maturity: episode.maturity }}
                    storyId={storyId}
                  />
                )}
              </div>
            )}

            {/* Internal GM Description */}
            <div className="space-y-1.5">
              <Label htmlFor="episode-description">Internal GM Description</Label>
              <Textarea
                id="episode-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="GM-only notes about this episode…"
                rows={2}
              />
              <p className="text-xs text-muted-foreground">Not shown to players.</p>
              {fieldErrors.description && (
                <p className="text-xs text-destructive">{fieldErrors.description.join(' ')}</p>
              )}
            </div>

            {/* The Story So Far (player-facing summary) */}
            <div className="space-y-1.5">
              <Label htmlFor="episode-summary">The Story So Far</Label>
              <Textarea
                id="episode-summary"
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                placeholder="What players know so far…"
                rows={2}
              />
              <p className="text-xs text-muted-foreground">
                Player-facing recap — keep this current as the story advances.
              </p>
              {fieldErrors.summary && (
                <p className="text-xs text-destructive">{fieldErrors.summary.join(' ')}</p>
              )}
            </div>

            {/* Resting conclusion (player-facing) */}
            <div className="space-y-1.5">
              <Label htmlFor="episode-resting-conclusion">Resting conclusion (player-facing)</Label>
              <Textarea
                id="episode-resting-conclusion"
                value={restingConclusion}
                onChange={(e) => setRestingConclusion(e.target.value)}
                placeholder="How the story reads if it rests here…"
                rows={2}
              />
              <p className="text-xs text-muted-foreground">
                Shown to players if the story rests here.
              </p>
              {fieldErrors.resting_conclusion && (
                <p className="text-xs text-destructive">
                  {fieldErrors.resting_conclusion.join(' ')}
                </p>
              )}
            </div>

            {/* Is ending */}
            <div className="space-y-1.5">
              <label className="flex cursor-pointer items-center gap-3 rounded-md border p-3">
                <input
                  type="checkbox"
                  checked={isEnding}
                  onChange={(e) => setIsEnding(e.target.checked)}
                  className="h-4 w-4"
                  id="episode-is-ending"
                />
                <span className="text-sm">This is an ending</span>
              </label>
              {fieldErrors.is_ending && (
                <p className="text-xs text-destructive">{fieldErrors.is_ending.join(' ')}</p>
              )}
            </div>

            {/* Order */}
            <div className="space-y-1.5">
              <Label htmlFor="episode-order">Order</Label>
              <Input
                id="episode-order"
                type="number"
                min={0}
                value={order}
                onChange={(e) => setOrder(e.target.value)}
                placeholder="e.g. 1"
              />
              {fieldErrors.order && (
                <p className="text-xs text-destructive">{fieldErrors.order.join(' ')}</p>
              )}
            </div>

            {/* Progression Requirements — only available for existing episodes */}
            {isEdit && episode ? (
              <ProgressionRequirementsEditor episodeId={episode.id} />
            ) : (
              <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                Save the episode first to add progression requirements.
              </div>
            )}
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending
                ? isEdit
                  ? 'Saving…'
                  : 'Creating…'
                : isEdit
                  ? 'Save Episode'
                  : 'Create Episode'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
