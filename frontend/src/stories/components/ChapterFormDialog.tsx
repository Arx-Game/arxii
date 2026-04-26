/**
 * ChapterFormDialog — create or edit a Chapter within a Story.
 *
 * Fields: title, description, order.
 * The parent story ID is passed in as context — not user-editable.
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
import { useCreateChapter, useUpdateChapter } from '../queries';
import type { Chapter } from '../types';

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  title?: string[];
  description?: string[];
  order?: string[];
  story?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

/** Minimum fields needed from a chapter object for the edit form. */
export interface ChapterLike {
  id: number;
  title: string;
  description?: string;
  order: number;
}

interface ChapterFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  storyId: number;
  /** When provided, dialog operates in edit mode. */
  chapter?: ChapterLike;
  onSuccess?: (chapter: Chapter) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ChapterFormDialog({
  open,
  onOpenChange,
  storyId,
  chapter,
  onSuccess,
}: ChapterFormDialogProps) {
  const isEdit = chapter !== undefined;

  const [title, setTitle] = useState(chapter?.title ?? '');
  const [description, setDescription] = useState(chapter?.description ?? '');
  const [order, setOrder] = useState<string>(
    chapter?.order !== undefined ? String(chapter.order) : ''
  );
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const createMutation = useCreateChapter();
  const updateMutation = useUpdateChapter();
  const isPending = createMutation.isPending || updateMutation.isPending;

  function resetForm() {
    setTitle(chapter?.title ?? '');
    setDescription(chapter?.description ?? '');
    setOrder(chapter?.order !== undefined ? String(chapter.order) : '');
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
      story: storyId,
      title: title.trim(),
      description: description.trim() || undefined,
      order: order !== '' ? Number(order) : undefined,
    };

    if (isEdit && chapter) {
      updateMutation.mutate(
        { id: chapter.id, data },
        {
          onSuccess: (updated) => {
            toast.success('Chapter updated');
            handleOpenChange(false);
            onSuccess?.(updated);
          },
          onError: handleError,
        }
      );
    } else {
      createMutation.mutate(data, {
        onSuccess: (created) => {
          toast.success('Chapter created');
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
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{isEdit ? 'Edit Chapter' : 'Create Chapter'}</DialogTitle>
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
              <Label htmlFor="chapter-title">
                Title <span className="text-destructive">*</span>
              </Label>
              <Input
                id="chapter-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Chapter title"
                required
              />
              {fieldErrors.title && (
                <p className="text-xs text-destructive">{fieldErrors.title.join(' ')}</p>
              )}
            </div>

            {/* Description */}
            <div className="space-y-1.5">
              <Label htmlFor="chapter-description">Description</Label>
              <Textarea
                id="chapter-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Chapter description…"
                rows={2}
              />
              {fieldErrors.description && (
                <p className="text-xs text-destructive">{fieldErrors.description.join(' ')}</p>
              )}
            </div>

            {/* Order */}
            <div className="space-y-1.5">
              <Label htmlFor="chapter-order">Order</Label>
              <Input
                id="chapter-order"
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
                  ? 'Save Chapter'
                  : 'Create Chapter'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
