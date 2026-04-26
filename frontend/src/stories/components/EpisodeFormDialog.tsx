/**
 * EpisodeFormDialog — create or edit an Episode within a Chapter.
 *
 * Fields: title, description, order.
 * Also embeds ProgressionRequirementsEditor for existing episodes (Task 9.4).
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
import type { Episode } from '../types';
import { ProgressionRequirementsEditor } from './ProgressionRequirementsEditor';

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  title?: string[];
  description?: string[];
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
  order: number;
}

interface EpisodeFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chapterId: number;
  /** When provided, dialog operates in edit mode. */
  episode?: EpisodeLike;
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
  onSuccess,
}: EpisodeFormDialogProps) {
  const isEdit = episode !== undefined;

  const [title, setTitle] = useState(episode?.title ?? '');
  const [description, setDescription] = useState(episode?.description ?? '');
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

            {/* Description */}
            <div className="space-y-1.5">
              <Label htmlFor="episode-description">Description</Label>
              <Textarea
                id="episode-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Episode description…"
                rows={2}
              />
              {fieldErrors.description && (
                <p className="text-xs text-destructive">{fieldErrors.description.join(' ')}</p>
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
