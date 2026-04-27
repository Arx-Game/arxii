/**
 * BulletinPostCard — renders a single bulletin post with its inline replies.
 *
 * Features:
 * - Header: title, author persona, relative time
 * - Edit / Delete buttons for GM/staff
 * - Body (whitespace-preserving plain text)
 * - Inline reply list (collapsed to first 3; "Show all" toggle)
 * - "+ Reply" inline form (if allow_replies AND viewer can reply)
 * - Inline edit form for the post itself
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { formatRelativeTime } from '@/lib/relativeTime';
import { useDeleteBulletinPost, useUpdateBulletinPost, useCreateBulletinReply } from '../queries';
import { BulletinReplyRow } from './BulletinReplyRow';
import type { TableBulletinPost } from '../types';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REPLIES_PREVIEW_COUNT = 3;

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFPostErrors {
  title?: string[];
  body?: string[];
  allow_replies?: string[];
  non_field_errors?: string[];
  detail?: string;
}

interface DRFReplyErrors {
  body?: string[];
  post?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface BulletinPostCardProps {
  post: TableBulletinPost;
  isGMOrStaff: boolean;
  /** PK of the Lead GM persona (needed when submitting a reply as the GM). */
  gmPersonaId?: number;
  /** Whether the viewer can reply (they have read access + allow_replies is true). */
  canReply: boolean;
  /** PK of the viewer's active persona for reply submission. */
  viewerPersonaId?: number;
}

// ---------------------------------------------------------------------------
// Inline post edit form
// ---------------------------------------------------------------------------

interface EditPostFormProps {
  post: TableBulletinPost;
  onCancel: () => void;
}

function EditPostForm({ post, onCancel }: EditPostFormProps) {
  const [title, setTitle] = useState(post.title);
  const [body, setBody] = useState(post.body);
  const [allowReplies, setAllowReplies] = useState(post.allow_replies);
  const [fieldErrors, setFieldErrors] = useState<DRFPostErrors>({});

  const updateMutation = useUpdateBulletinPost();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});
    updateMutation.mutate(
      {
        id: post.id,
        data: { title: title.trim(), body: body.trim(), allow_replies: allowReplies },
        tableId: post.table,
      },
      {
        onSuccess: () => {
          toast.success('Post updated');
          onCancel();
        },
        onError: async (err: unknown) => {
          const res = (err as { response?: Response })?.response;
          if (res) {
            const errBody = (await res.json()) as DRFPostErrors;
            setFieldErrors(errBody);
          }
        },
      }
    );
  }

  const isValid = title.trim().length > 0 && body.trim().length > 0;

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="space-y-3 rounded border p-4">
      <div className="space-y-1">
        <Label htmlFor={`post-title-${post.id}`}>Title *</Label>
        <Input
          id={`post-title-${post.id}`}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
          required
        />
        {fieldErrors.title && (
          <p className="text-sm text-destructive">{fieldErrors.title.join(' ')}</p>
        )}
      </div>

      <div className="space-y-1">
        <Label htmlFor={`post-body-${post.id}`}>Body *</Label>
        <Textarea
          id={`post-body-${post.id}`}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={5}
          required
        />
        {fieldErrors.body && (
          <p className="text-sm text-destructive">{fieldErrors.body.join(' ')}</p>
        )}
      </div>

      <div className="flex items-center gap-2">
        <input
          id={`post-allow-replies-${post.id}`}
          type="checkbox"
          checked={allowReplies}
          onChange={(e) => setAllowReplies(e.target.checked)}
          className="h-4 w-4 rounded border"
        />
        <Label htmlFor={`post-allow-replies-${post.id}`}>Allow replies</Label>
      </div>

      {fieldErrors.non_field_errors && (
        <p className="text-sm text-destructive">{fieldErrors.non_field_errors.join(' ')}</p>
      )}
      {fieldErrors.detail && <p className="text-sm text-destructive">{fieldErrors.detail}</p>}

      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={!isValid || updateMutation.isPending}>
          {updateMutation.isPending ? 'Saving…' : 'Save Changes'}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Inline reply form
// ---------------------------------------------------------------------------

interface ReplyFormProps {
  postId: number;
  viewerPersonaId: number;
  onCancel: () => void;
}

function ReplyForm({ postId, viewerPersonaId, onCancel }: ReplyFormProps) {
  const [body, setBody] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFReplyErrors>({});

  const createMutation = useCreateBulletinReply();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});
    createMutation.mutate(
      { post: postId, author_persona: viewerPersonaId, body: body.trim() },
      {
        onSuccess: () => {
          toast.success('Reply posted');
          onCancel();
        },
        onError: async (err: unknown) => {
          const res = (err as { response?: Response })?.response;
          if (res) {
            const errBody = (await res.json()) as DRFReplyErrors;
            setFieldErrors(errBody);
          }
        },
      }
    );
  }

  const isValid = body.trim().length > 0;

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="space-y-2 pl-6">
      <Textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Write a reply…"
        rows={3}
        aria-label="Reply body"
      />
      {fieldErrors.body && <p className="text-sm text-destructive">{fieldErrors.body.join(' ')}</p>}
      {fieldErrors.non_field_errors && (
        <p className="text-sm text-destructive">{fieldErrors.non_field_errors.join(' ')}</p>
      )}
      {fieldErrors.detail && <p className="text-sm text-destructive">{fieldErrors.detail}</p>}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={!isValid || createMutation.isPending}>
          {createMutation.isPending ? 'Posting…' : 'Post Reply'}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// BulletinPostCard
// ---------------------------------------------------------------------------

export function BulletinPostCard({
  post,
  isGMOrStaff,
  canReply,
  viewerPersonaId,
}: BulletinPostCardProps) {
  const [editing, setEditing] = useState(false);
  const [showAllReplies, setShowAllReplies] = useState(false);
  const [showReplyForm, setShowReplyForm] = useState(false);

  const deleteMutation = useDeleteBulletinPost();

  function handleDelete() {
    deleteMutation.mutate(
      { id: post.id, tableId: post.table },
      {
        onSuccess: () => {
          toast.success('Post deleted');
        },
        onError: () => {
          toast.error('Failed to delete post. Please try again.');
        },
      }
    );
  }

  const authorName = post.author_persona_name ?? `Persona #${post.author_persona}`;
  const replies = post.replies ?? [];
  const hasMoreReplies = replies.length > REPLIES_PREVIEW_COUNT;
  const visibleReplies = showAllReplies ? replies : replies.slice(0, REPLIES_PREVIEW_COUNT);

  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm">
      {editing ? (
        <EditPostForm post={post} onCancel={() => setEditing(false)} />
      ) : (
        <>
          {/* Header */}
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h3 className="font-semibold leading-tight">{post.title}</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                <span className="font-medium">{authorName}</span>
                {' · '}
                <span title={post.created_at}>{formatRelativeTime(post.created_at)}</span>
                {post.updated_at !== post.created_at && (
                  <span className="italic" title={post.updated_at}>
                    {' '}
                    (edited)
                  </span>
                )}
              </p>
            </div>

            {isGMOrStaff && (
              <div className="flex shrink-0 gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs"
                  onClick={() => setEditing(true)}
                >
                  Edit
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs text-destructive hover:text-destructive"
                  onClick={handleDelete}
                  disabled={deleteMutation.isPending}
                >
                  Delete
                </Button>
              </div>
            )}
          </div>

          {/* Separator */}
          <hr className="my-3" />

          {/* Body */}
          <p className="whitespace-pre-wrap text-sm">{post.body}</p>

          {/* Replies section */}
          {replies.length > 0 && (
            <div className="mt-4 space-y-0.5 border-t pt-3">
              <p className="mb-1 text-xs font-medium text-muted-foreground">
                {replies.length} {replies.length === 1 ? 'reply' : 'replies'}
              </p>
              {visibleReplies.map((reply) => (
                <BulletinReplyRow key={reply.id} reply={reply} isGMOrStaff={isGMOrStaff} />
              ))}
              {hasMoreReplies && !showAllReplies && (
                <button
                  type="button"
                  className="mt-1 text-xs text-muted-foreground hover:underline"
                  onClick={() => setShowAllReplies(true)}
                >
                  Show {replies.length - REPLIES_PREVIEW_COUNT} more{' '}
                  {replies.length - REPLIES_PREVIEW_COUNT === 1 ? 'reply' : 'replies'}
                </button>
              )}
              {showAllReplies && hasMoreReplies && (
                <button
                  type="button"
                  className="mt-1 text-xs text-muted-foreground hover:underline"
                  onClick={() => setShowAllReplies(false)}
                >
                  Show fewer
                </button>
              )}
            </div>
          )}

          {/* Reply form / button */}
          {canReply && post.allow_replies && (
            <div className="mt-3 border-t pt-3">
              {showReplyForm ? (
                viewerPersonaId !== undefined ? (
                  <ReplyForm
                    postId={post.id}
                    viewerPersonaId={viewerPersonaId}
                    onCancel={() => setShowReplyForm(false)}
                  />
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No active persona available for replies.
                  </p>
                )
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setShowReplyForm(true)}
                >
                  + Reply
                </Button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

export function BulletinPostCardSkeleton() {
  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm">
      <Skeleton className="mb-2 h-5 w-48" />
      <Skeleton className="h-3 w-32" />
      <hr className="my-3" />
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    </div>
  );
}
