/**
 * CreateBulletinPostDialog — GM/staff creates a new bulletin post.
 *
 * Fields:
 *   - Title (required, max 200)
 *   - Body (required)
 *   - Story selector: "Table-Wide" (null) or a specific story PK
 *   - Allow replies (checkbox, default true)
 *
 * The Lead GM's persona PK must be passed as `gmPersonaId`.
 */

import { useState, useEffect } from 'react';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useCreateBulletinPost } from '../queries';
import type { StoryList } from '@/stories/types';

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFErrors {
  title?: string[];
  body?: string[];
  story?: string[];
  allow_replies?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface CreateBulletinPostDialogProps {
  tableId: number;
  /** The Lead GM's persona PK — required for author_persona in the POST body. */
  gmPersonaId: number;
  /** Stories at this table (for the section selector in the form). */
  stories: StoryList[];
  /** Initial story to pre-select (optional — e.g., when opened from a story tab). */
  initialStoryId?: number | null;
  children: React.ReactNode;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CreateBulletinPostDialog({
  tableId,
  gmPersonaId,
  stories,
  initialStoryId,
  children,
}: CreateBulletinPostDialogProps) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  /** "table-wide" means null story; otherwise story PK as string. */
  const [storyValue, setStoryValue] = useState<string>('table-wide');
  const [allowReplies, setAllowReplies] = useState(true);
  const [fieldErrors, setFieldErrors] = useState<DRFErrors>({});

  const createMutation = useCreateBulletinPost();

  // Pre-select story when prop changes (e.g., opening from a story tab).
  useEffect(() => {
    if (open) {
      setStoryValue(initialStoryId != null ? String(initialStoryId) : 'table-wide');
    }
  }, [open, initialStoryId]);

  function resetForm() {
    setTitle('');
    setBody('');
    setStoryValue(initialStoryId != null ? String(initialStoryId) : 'table-wide');
    setAllowReplies(true);
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});

    const storyId = storyValue === 'table-wide' ? null : parseInt(storyValue, 10);

    createMutation.mutate(
      {
        table: tableId,
        story: storyId,
        author_persona: gmPersonaId,
        title: title.trim(),
        body: body.trim(),
        allow_replies: allowReplies,
      },
      {
        onSuccess: () => {
          toast.success('Post created');
          setOpen(false);
        },
        onError: async (err: unknown) => {
          const res = (err as { response?: Response })?.response;
          if (res) {
            const errBody = (await res.json()) as DRFErrors;
            setFieldErrors(errBody);
          }
        },
      }
    );
  }

  const isValid = title.trim().length > 0 && body.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New Bulletin Post</DialogTitle>
          <DialogDescription>
            Create a post visible to table members. Choose a section to scope it to a specific
            story, or leave as Table-Wide.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          {/* Title */}
          <div className="space-y-1">
            <Label htmlFor="bp-title">Title *</Label>
            <Input
              id="bp-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Session next Tuesday"
              maxLength={200}
              required
              aria-describedby={fieldErrors.title ? 'bp-title-error' : undefined}
            />
            {fieldErrors.title && (
              <p id="bp-title-error" className="text-sm text-destructive">
                {fieldErrors.title.join(' ')}
              </p>
            )}
          </div>

          {/* Body */}
          <div className="space-y-1">
            <Label htmlFor="bp-body">Body *</Label>
            <Textarea
              id="bp-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Write your announcement…"
              rows={5}
              required
              aria-describedby={fieldErrors.body ? 'bp-body-error' : undefined}
            />
            {fieldErrors.body && (
              <p id="bp-body-error" className="text-sm text-destructive">
                {fieldErrors.body.join(' ')}
              </p>
            )}
          </div>

          {/* Section selector */}
          <div className="space-y-1">
            <Label htmlFor="bp-story">Section</Label>
            <Select value={storyValue} onValueChange={setStoryValue}>
              <SelectTrigger id="bp-story">
                <SelectValue placeholder="Table-Wide" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="table-wide">Table-Wide</SelectItem>
                {stories.map((story) => (
                  <SelectItem key={story.id} value={String(story.id)}>
                    {story.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {fieldErrors.story && (
              <p className="text-sm text-destructive">{fieldErrors.story.join(' ')}</p>
            )}
          </div>

          {/* Allow replies */}
          <div className="flex items-center gap-2">
            <input
              id="bp-allow-replies"
              type="checkbox"
              checked={allowReplies}
              onChange={(e) => setAllowReplies(e.target.checked)}
              className="h-4 w-4 rounded border"
            />
            <Label htmlFor="bp-allow-replies">Allow replies from members</Label>
          </div>

          {/* Global errors */}
          {fieldErrors.non_field_errors && (
            <p className="text-sm text-destructive">{fieldErrors.non_field_errors.join(' ')}</p>
          )}
          {fieldErrors.detail && <p className="text-sm text-destructive">{fieldErrors.detail}</p>}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!isValid || createMutation.isPending}>
              {createMutation.isPending ? 'Posting…' : 'Create Post'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
