/**
 * BulletinReplyRow — renders a single reply on a bulletin post.
 *
 * Shows: author persona name, body, relative time.
 * Edit/Delete: visible to GM/staff (isGMOrStaff prop).
 * Inline edit form opens in-place when [Edit] is clicked.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { formatRelativeTime } from '@/lib/relativeTime';
import { useDeleteBulletinReply, useUpdateBulletinReply } from '../queries';
import type { TableBulletinReply } from '../types';

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFErrors {
  body?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface BulletinReplyRowProps {
  reply: TableBulletinReply;
  isGMOrStaff: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function BulletinReplyRow({ reply, isGMOrStaff }: BulletinReplyRowProps) {
  const [editing, setEditing] = useState(false);
  const [editBody, setEditBody] = useState(reply.body);
  const [fieldErrors, setFieldErrors] = useState<DRFErrors>({});

  const updateMutation = useUpdateBulletinReply();
  const deleteMutation = useDeleteBulletinReply();

  function handleEdit() {
    setEditBody(reply.body);
    setFieldErrors({});
    setEditing(true);
  }

  function handleCancelEdit() {
    setEditing(false);
    setFieldErrors({});
  }

  function handleSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});
    updateMutation.mutate(
      { id: reply.id, data: { body: editBody.trim() }, postId: reply.post },
      {
        onSuccess: () => {
          setEditing(false);
          toast.success('Reply updated');
        },
        onError: async (err: unknown) => {
          const res = (err as { response?: Response })?.response;
          if (res) {
            const body = (await res.json()) as DRFErrors;
            setFieldErrors(body);
          }
        },
      }
    );
  }

  function handleDelete() {
    deleteMutation.mutate(
      { id: reply.id, postId: reply.post },
      {
        onSuccess: () => {
          toast.success('Reply deleted');
        },
        onError: () => {
          toast.error('Failed to delete reply. Please try again.');
        },
      }
    );
  }

  const authorName = reply.author_persona_name ?? `Persona #${reply.author_persona}`;

  return (
    <div className="flex gap-2 py-2 text-sm">
      {/* Left dash / thread indicator */}
      <span className="mt-0.5 shrink-0 text-muted-foreground">—</span>

      <div className="min-w-0 flex-1 space-y-1">
        {/* Header row */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{authorName}</span>
          <span className="text-xs text-muted-foreground" title={reply.created_at}>
            {formatRelativeTime(reply.created_at)}
          </span>
          {isGMOrStaff && !editing && (
            <span className="ml-auto flex gap-1">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-5 px-1 text-xs"
                onClick={handleEdit}
              >
                Edit
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-5 px-1 text-xs text-destructive hover:text-destructive"
                onClick={handleDelete}
                disabled={deleteMutation.isPending}
              >
                Delete
              </Button>
            </span>
          )}
        </div>

        {/* Body / inline edit form */}
        {editing ? (
          <form onSubmit={(e) => void handleSaveEdit(e)} className="space-y-2">
            <Textarea
              value={editBody}
              onChange={(e) => setEditBody(e.target.value)}
              rows={2}
              className="text-sm"
              aria-label="Edit reply"
            />
            {fieldErrors.body && (
              <p className="text-xs text-destructive">{fieldErrors.body.join(' ')}</p>
            )}
            {fieldErrors.non_field_errors && (
              <p className="text-xs text-destructive">{fieldErrors.non_field_errors.join(' ')}</p>
            )}
            {fieldErrors.detail && <p className="text-xs text-destructive">{fieldErrors.detail}</p>}
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={updateMutation.isPending}>
                {updateMutation.isPending ? 'Saving…' : 'Save'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={handleCancelEdit}>
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          <p className="whitespace-pre-wrap text-sm">{reply.body}</p>
        )}
      </div>
    </div>
  );
}
