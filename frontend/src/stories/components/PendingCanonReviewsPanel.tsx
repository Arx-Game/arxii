/**
 * PendingCanonReviewsPanel — staff queue for pending canon-impact reviews
 * (#2003/#3304), mounted on StaffWorkloadPage.
 *
 * The list itself is not fetched separately: it rides
 * StaffWorkloadResponse.pending_canon_reviews (already built for #2003, just
 * never rendered). Only the two decision actions (clear / request changes)
 * are new — both reuse ClearanceNoteDialog (`clearanceShared.tsx`), the same
 * generic note-dialog the custody-clearance grant/deny/resolve actions use,
 * rather than hand-rolling a third copy of the same open/note/error dialog
 * shape.
 */

import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { formatRelativeTime } from '@/lib/relativeTime';
import { useClearCanonReview, useRequestCanonReviewChanges } from '../queries';
import type { PendingCanonReviewEntry } from '../types';
import { ClearanceNoteDialog, handleInlineError } from './clearanceShared';

interface PendingCanonReviewsPanelProps {
  entries: PendingCanonReviewEntry[];
}

const TIER_LABELS: Record<string, string> = {
  table: 'Table',
  regional: 'Regional',
  world: 'World',
};

function TierBadge({ tier }: { tier: string }) {
  const isWorld = tier === 'world';
  return (
    <span
      className={
        isWorld
          ? 'rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive'
          : 'rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground'
      }
    >
      {TIER_LABELS[tier] ?? tier}
    </span>
  );
}

function ReviewRow({ entry }: { entry: PendingCanonReviewEntry }) {
  const clearMutation = useClearCanonReview();
  const changesMutation = useRequestCanonReviewChanges();

  return (
    <tr className="border-b last:border-0 hover:bg-accent/50" data-testid="pending-canon-review-row">
      <td className="py-3 pr-4">
        <Link
          to={`/stories/${entry.story_id}`}
          className="font-medium text-primary hover:underline"
        >
          {entry.story_title}
        </Link>
      </td>
      <td className="py-3 pr-4">
        <TierBadge tier={entry.tier} />
      </td>
      <td className="py-3 pr-4 text-muted-foreground">{formatRelativeTime(entry.created_at)}</td>
      <td className="py-3 pr-4 tabular-nums">{entry.days_aging}</td>
      <td className="py-3">
        <div className="flex gap-2">
          <ClearanceNoteDialog
            title="Clear canon review"
            noteLabel="Notes"
            placeholder="Any notes for the record…"
            submitLabel="Clear"
            pendingLabel="Clearing…"
            isPending={clearMutation.isPending}
            successToast="Canon review cleared"
            errorFallback="Failed to clear canon review."
            triggerTestId="clear-canon-review-btn"
            triggerLabel="Clear"
            onSubmit={(notes, { setError, close }) => {
              clearMutation.mutate(
                { reviewId: entry.review_id, body: { notes } },
                {
                  onSuccess: () => {
                    toast.success('Canon review cleared');
                    close();
                  },
                  onError: (err) =>
                    handleInlineError(err, setError, 'Failed to clear canon review.'),
                }
              );
            }}
          />
          <ClearanceNoteDialog
            title="Request changes"
            noteLabel="Notes"
            placeholder="What needs to change before this can clear…"
            submitLabel="Request Changes"
            pendingLabel="Sending…"
            isPending={changesMutation.isPending}
            successToast="Changes requested"
            errorFallback="Failed to request changes."
            submitVariant="destructive"
            triggerTestId="request-canon-review-changes-btn"
            triggerLabel="Request Changes"
            triggerVariant="outline"
            noteRequired
            requiredErrorMessage="Notes are required so the Lead GM knows what to change."
            onSubmit={(notes, { setError, close }) => {
              changesMutation.mutate(
                { reviewId: entry.review_id, body: { notes } },
                {
                  onSuccess: () => {
                    toast.success('Changes requested');
                    close();
                  },
                  onError: (err) => handleInlineError(err, setError, 'Failed to request changes.'),
                }
              );
            }}
          />
        </div>
      </td>
    </tr>
  );
}

export function PendingCanonReviewsPanel({ entries }: PendingCanonReviewsPanelProps) {
  if (entries.length === 0) {
    return (
      <p className="py-4 text-muted-foreground" data-testid="pending-canon-reviews-empty">
        No canon reviews are pending.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto" data-testid="pending-canon-reviews-table">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="pb-2 pr-4 font-medium">Story</th>
            <th className="pb-2 pr-4 font-medium">Tier</th>
            <th className="pb-2 pr-4 font-medium">Requested</th>
            <th className="pb-2 pr-4 font-medium">Days Aging</th>
            <th className="pb-2 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <ReviewRow key={entry.review_id} entry={entry} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
