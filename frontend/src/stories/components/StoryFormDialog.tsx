/**
 * StoryFormDialog — create or edit a Story.
 *
 * Fields: title, description (internal GM), summary ("The Story So Far",
 * player-facing), scope (CHARACTER / GROUP / GLOBAL). On edit, the current
 * maturity is shown read-only (promotion is a separate control).
 * Validation errors from DRF are surfaced inline next to their fields.
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { useCreateStory, useUpdateStory } from '../queries';
import type { Story, StoryScope } from '../types';

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  title?: string[];
  description?: string[];
  summary?: string[];
  scope?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface StoryFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When provided, dialog operates in edit mode. */
  story?: Story;
  onSuccess?: (story: Story) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StoryFormDialog({ open, onOpenChange, story, onSuccess }: StoryFormDialogProps) {
  const isEdit = story !== undefined;

  const [title, setTitle] = useState(story?.title ?? '');
  const [description, setDescription] = useState(story?.description ?? '');
  const [summary, setSummary] = useState(story?.summary ?? '');
  const [scope, setScope] = useState<StoryScope>(story?.scope ?? 'character');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const createMutation = useCreateStory();
  const updateMutation = useUpdateStory();

  const isPending = createMutation.isPending || updateMutation.isPending;

  function resetForm() {
    setTitle(story?.title ?? '');
    setDescription(story?.description ?? '');
    setSummary(story?.summary ?? '');
    setScope(story?.scope ?? 'character');
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
            if (data && typeof data === 'object') {
              setFieldErrors(data as DRFFieldErrors);
            }
          })
          .catch(() => toast.error('An error occurred. Please try again.'));
        return;
      }
    }
    const message = err instanceof Error ? err.message : 'An error occurred. Please try again.';
    toast.error(message);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});

    const data = {
      title: title.trim(),
      description: description.trim(),
      summary: summary.trim(),
      scope,
    };

    if (isEdit && story) {
      updateMutation.mutate(
        { id: story.id, data },
        {
          onSuccess: (updated) => {
            toast.success('Story updated');
            handleOpenChange(false);
            onSuccess?.(updated);
          },
          onError: handleError,
        }
      );
    } else {
      createMutation.mutate(data, {
        onSuccess: (created) => {
          toast.success('Story created');
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
            <DialogTitle>{isEdit ? 'Edit Story' : 'Create Story'}</DialogTitle>
          </DialogHeader>

          {/* Non-field errors */}
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
              <Label htmlFor="story-title">
                Title <span className="text-destructive">*</span>
              </Label>
              <Input
                id="story-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Story title"
                required
              />
              {fieldErrors.title && (
                <p className="text-xs text-destructive">{fieldErrors.title.join(' ')}</p>
              )}
            </div>

            {/* Maturity (read-only, edit mode only) */}
            {isEdit && story?.maturity && (
              <div
                data-testid="story-maturity-indicator"
                className="inline-flex w-fit items-center rounded-md border bg-muted px-2 py-1 text-xs text-muted-foreground"
              >
                Maturity: <span className="ml-1 font-medium capitalize">{story.maturity}</span>
              </div>
            )}

            {/* Internal GM Description */}
            <div className="space-y-1.5">
              <Label htmlFor="story-description">Internal GM Description</Label>
              <Textarea
                id="story-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="GM-only notes about this story…"
                rows={3}
              />
              <p className="text-xs text-muted-foreground">Not shown to players.</p>
              {fieldErrors.description && (
                <p className="text-xs text-destructive">{fieldErrors.description.join(' ')}</p>
              )}
            </div>

            {/* The Story So Far (player-facing summary) */}
            <div className="space-y-1.5">
              <Label htmlFor="story-summary">The Story So Far</Label>
              <Textarea
                id="story-summary"
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                placeholder="What players know so far…"
                rows={3}
              />
              <p className="text-xs text-muted-foreground">
                Player-facing recap — keep this current as the story advances.
              </p>
              {fieldErrors.summary && (
                <p className="text-xs text-destructive">{fieldErrors.summary.join(' ')}</p>
              )}
            </div>

            {/* Scope */}
            <div className="space-y-2">
              <Label>Scope</Label>
              <RadioGroup
                value={scope}
                onValueChange={(val) => setScope(val as StoryScope)}
                className="flex flex-col gap-2"
              >
                {(
                  [
                    ['character', "Character — one character's personal story"],
                    ['group', "Group — a covenant or table's story"],
                    ['global', 'Global — affects the whole metaplot'],
                  ] as const
                ).map(([value, label]) => (
                  <label
                    key={value}
                    className="flex cursor-pointer items-center gap-3 rounded-md border p-3 hover:bg-accent"
                  >
                    <RadioGroupItem value={value} id={`scope-${value}`} />
                    <span className="text-sm">{label}</span>
                  </label>
                ))}
              </RadioGroup>
              {fieldErrors.scope && (
                <p className="text-xs text-destructive">{fieldErrors.scope.join(' ')}</p>
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
                  ? 'Save Story'
                  : 'Create Story'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
