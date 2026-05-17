/**
 * GMNotesPanel — Task E5
 *
 * Surfaces the backbone's story-scoped append-only StoryNote ledger as the
 * "viewable list for other GMs with timestamps" from the design. Read-only
 * list + append form; no edit/delete (the API is append-only).
 *
 * Auth is enforced server-side (CanAccessStoryNotes: staff, story owner, or
 * active/Lead GM of the story); the author page is already GM-gated, so this
 * panel does not re-implement auth — it just renders the list + append form.
 *
 * The StoryNote API is paginated (PaginatedResponse<StoryNote>); we read
 * `results`. backbone's StoryNoteViewSet orders `-created_at`, so the API
 * order is already newest-first — we render in returned order.
 *
 * The create endpoint 400s with standard DRF field errors
 * (`{ body: ["<message>"] }`) or `{ non_field_errors: [...] }` /
 * `{ detail: "<message>" }`. The design wants that surfaced INLINE so the GM
 * sees exactly why it failed — not a transient toast. We mirror the
 * DRF-400-surfacing mechanism used by PromoteMaturityButton: the apiFetch
 * error object carries the failed `Response`; `response.json()` resolves to
 * the DRF error body, which we read and render inline.
 *
 * Success relies on the hook's query invalidation (useCreateStoryNote
 * invalidates the storyNotes(story) cache); no manual refetch.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { formatRelativeTime } from '@/lib/relativeTime';
import { useCreateStoryNote, useStoryNotes } from '../queries';
import type { StoryNote } from '../types';

// ---------------------------------------------------------------------------
// DRF error shape — the create action 400s with standard field errors
// (`body` may arrive as string | string[]), or non_field_errors / detail.
// ---------------------------------------------------------------------------

interface StoryNoteDRFError {
  body?: string | string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface GMNotesPanelProps {
  storyId: number;
}

// ---------------------------------------------------------------------------
// Single note row
// ---------------------------------------------------------------------------

function NoteRow({ note }: { note: StoryNote }) {
  const author = note.author_account != null ? `Account #${note.author_account}` : 'Unknown author';

  return (
    <li className="rounded-md border bg-muted/30 p-3" data-testid="gm-note-row">
      <p className="whitespace-pre-wrap text-sm text-foreground/90">{note.body}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>{author}</span>
        <span aria-hidden>·</span>
        <time data-testid="gm-note-time" dateTime={note.created_at} title={note.created_at}>
          {formatRelativeTime(note.created_at)}
        </time>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function GMNotesPanel({ storyId }: GMNotesPanelProps) {
  const { data, isLoading } = useStoryNotes(storyId);
  const createMutation = useCreateStoryNote();

  const [body, setBody] = useState('');
  const [inlineError, setInlineError] = useState('');

  const notes = data?.results ?? [];
  const trimmed = body.trim();
  const canSubmit = trimmed.length > 0 && !createMutation.isPending;

  function handleError(err: unknown) {
    if (err && typeof err === 'object' && 'response' in err) {
      const response = (err as { response?: { json: () => Promise<unknown> } }).response;
      if (response) {
        void response
          .json()
          .then((parsed: unknown) => {
            if (parsed && typeof parsed === 'object') {
              const drf = parsed as StoryNoteDRFError;
              const bodyErr = Array.isArray(drf.body) ? drf.body.join(' ') : drf.body;
              const message =
                bodyErr ||
                drf.non_field_errors?.join(' ') ||
                drf.detail ||
                'Failed to add note. Please try again.';
              setInlineError(message);
            } else {
              setInlineError('Failed to add note. Please try again.');
            }
          })
          .catch(() => setInlineError('Failed to add note. Please try again.'));
        return;
      }
    }
    setInlineError(err instanceof Error ? err.message : 'Failed to add note. Please try again.');
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    // Clear any prior error before the new attempt.
    setInlineError('');
    createMutation.mutate(
      { story: storyId, body: trimmed },
      {
        onSuccess: () => {
          setInlineError('');
          setBody('');
          toast.success('Note added');
        },
        onError: handleError,
      }
    );
  }

  return (
    <div className="space-y-4" data-testid="gm-notes-panel">
      <p className="text-sm text-muted-foreground">
        Append-only authorial memory shared with this story&apos;s GMs. Notes cannot be edited or
        deleted.
      </p>

      {/* Notes list */}
      {isLoading ? (
        <div className="space-y-2" data-testid="gm-notes-loading">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : notes.length === 0 ? (
        <p className="text-sm italic text-muted-foreground" data-testid="gm-notes-empty">
          No GM notes yet. Add the first one below.
        </p>
      ) : (
        <ul className="space-y-2" data-testid="gm-notes-list">
          {notes.map((note) => (
            <NoteRow key={note.id} note={note} />
          ))}
        </ul>
      )}

      {/* Append form */}
      <form onSubmit={handleSubmit} className="space-y-2" data-testid="gm-note-form">
        <Textarea
          data-testid="gm-note-body"
          aria-label="New GM note"
          placeholder="Add an authorial note for this story's GMs…"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={3}
        />
        {inlineError && (
          <p data-testid="gm-note-error" className="text-xs text-destructive">
            {inlineError}
          </p>
        )}
        <div className="flex justify-end">
          <Button type="submit" size="sm" disabled={!canSubmit}>
            {createMutation.isPending ? 'Adding…' : 'Add Note'}
          </Button>
        </div>
      </form>
    </div>
  );
}
