/**
 * MyClaimRow — a single AGM claim row in the My AGM Claims page.
 *
 * Wave 7: AGM perspective.
 *
 * Renders differently based on claim status:
 *   REQUESTED  — shows "Cancel" button
 *   APPROVED   — shows framing_note + "Mark Beat" CTA
 *   REJECTED   — shows rejection_note (read-only)
 *   COMPLETED  — read-only history entry
 *   CANCELLED  — read-only history entry
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { formatRelativeTime } from '@/lib/relativeTime';
import { useCancelClaim, useBeat } from '../queries';
import { MarkBeatDialog } from './MarkBeatDialog';
import type { AssistantGMClaim, AssistantClaimStatus } from '../types';

// ---------------------------------------------------------------------------
// Status badge styling
// ---------------------------------------------------------------------------

const STATUS_LABELS: Record<AssistantClaimStatus, string> = {
  requested: 'Requested',
  approved: 'Approved',
  rejected: 'Rejected',
  completed: 'Completed',
  cancelled: 'Cancelled',
};

const STATUS_CLASSES: Record<AssistantClaimStatus, string> = {
  requested: 'bg-amber-600 text-white border-transparent',
  approved: 'bg-green-600 text-white border-transparent',
  rejected: 'bg-red-600 text-white border-transparent',
  completed: 'bg-blue-600 text-white border-transparent',
  cancelled: 'bg-gray-500 text-white border-transparent',
};

// ---------------------------------------------------------------------------
// Sub-component: approved claim body (with MarkBeat CTA)
// ---------------------------------------------------------------------------

function ApprovedClaimBody({ claim }: { claim: AssistantGMClaim }) {
  // Fetch the full Beat so MarkBeatDialog can use it
  const { data: beat, isLoading } = useBeat(claim.beat);

  return (
    <div className="mt-2 space-y-2">
      {claim.framing_note && (
        <div className="rounded-md bg-muted px-3 py-2 text-sm">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Lead GM framing
          </p>
          <p className="text-foreground">{claim.framing_note}</p>
        </div>
      )}
      <div className="mt-2 flex items-center gap-2">
        {isLoading ? (
          <Button variant="outline" size="sm" disabled>
            Loading…
          </Button>
        ) : beat ? (
          <MarkBeatDialog beat={beat} />
        ) : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: cancel confirmation dialog
// ---------------------------------------------------------------------------

function CancelClaimButton({ claimId }: { claimId: number }) {
  const cancelMutation = useCancelClaim();

  function handleConfirm() {
    cancelMutation.mutate(claimId, {
      onSuccess: () => {
        toast.success('Claim cancelled');
      },
      onError: (err: unknown) => {
        const message = err instanceof Error ? err.message : 'Failed to cancel claim.';
        toast.error(message);
      },
    });
  }

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="outline" size="sm" disabled={cancelMutation.isPending}>
          {cancelMutation.isPending ? 'Cancelling…' : 'Cancel Claim'}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Cancel this claim?</AlertDialogTitle>
          <AlertDialogDescription>
            This will withdraw your claim request. You can submit a new claim on this beat later if
            it remains AGM-eligible.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep Claim</AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm}>Yes, Cancel</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface MyClaimRowProps {
  claim: AssistantGMClaim;
}

const EXCERPT_LENGTH = 150;

function beatExcerpt(text: string): string {
  if (text.length <= EXCERPT_LENGTH) return text;
  return text.slice(0, EXCERPT_LENGTH).trimEnd() + '…';
}

export function MyClaimRow({ claim }: MyClaimRowProps) {
  // Fetch beat for description — only used for the card header, so a lightweight
  // read. The beat is already in the identity map if MarkBeatDialog loaded it.
  const { data: beat } = useBeat(claim.beat);
  const [expanded, setExpanded] = useState(false);

  const status = claim.status as AssistantClaimStatus;
  const beatDescription = beat
    ? (beat.internal_description ?? beat.player_hint ?? `Beat #${claim.beat}`)
    : `Beat #${claim.beat}`;

  return (
    <Card data-testid="my-claim-row">
      <CardContent className="py-4">
        {/* Header */}
        <div className="flex flex-wrap items-center gap-2">
          <Badge className={STATUS_CLASSES[status]}>{STATUS_LABELS[status]}</Badge>
          <span className="text-sm text-muted-foreground">
            Requested {formatRelativeTime(claim.requested_at)}
          </span>
        </div>

        {/* Beat description */}
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 w-full text-left text-sm text-foreground hover:text-muted-foreground"
          data-testid="beat-description-toggle"
        >
          {expanded ? beatDescription : beatExcerpt(beatDescription)}
          {beatDescription.length > EXCERPT_LENGTH && (
            <span className="ml-1 text-xs text-muted-foreground">
              {expanded ? '(less)' : '(more)'}
            </span>
          )}
        </button>

        {/* Status-specific body */}
        {status === 'requested' && <CancelClaimButton claimId={claim.id} />}

        {status === 'approved' && <ApprovedClaimBody claim={claim} />}

        {status === 'rejected' && claim.rejection_note && (
          <div className="mt-2 rounded-md bg-red-50 px-3 py-2 text-sm dark:bg-red-950/30">
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-red-600 dark:text-red-400">
              Rejection note
            </p>
            <p className="text-foreground">{claim.rejection_note}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
