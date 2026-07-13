/**
 * CrossoverInviteCard — renders a single crossover invite (#2075).
 *
 * Context-dependent actions:
 * - Received PENDING: Accept (opens AcceptInviteDialog) + Decline
 * - Sent PENDING: Withdraw
 * - ACCEPTED/DECLINED/WITHDRAWN: read-only with status badge
 *
 * The caller passes `isSent` to distinguish sent vs. received invites.
 * Story and event display names are resolved via prefetched lists passed as props.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { AcceptInviteDialog } from './AcceptInviteDialog';
import { useDeclineCrossoverInvite, useWithdrawCrossoverInvite } from '../queries';
import type { CrossoverInvite, CrossoverInviteStatus } from '../types';

interface CrossoverInviteCardProps {
  invite: CrossoverInvite;
  /** True if this invite was sent by the current user (from_gm_account === account.id). */
  isSent: boolean;
  /** Resolved story title for to_story PK. */
  storyTitle?: string;
  /** Resolved event name for event PK. */
  eventTitle?: string;
}

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'default',
  accepted: 'secondary',
  declined: 'destructive',
  withdrawn: 'outline',
};

export function CrossoverInviteCard({
  invite,
  isSent,
  storyTitle,
  eventTitle,
}: CrossoverInviteCardProps) {
  const [acceptOpen, setAcceptOpen] = useState(false);
  const declineMutation = useDeclineCrossoverInvite();
  const withdrawMutation = useWithdrawCrossoverInvite();

  const status = invite.status as CrossoverInviteStatus;
  const isPending = status === 'pending';

  function handleDecline() {
    declineMutation.mutate(
      { id: invite.id },
      {
        onSuccess: () => toast.success('Invite declined'),
        onError: () => toast.error('Failed to decline invite. Please try again.'),
      }
    );
  }

  function handleWithdraw() {
    withdrawMutation.mutate(invite.id, {
      onSuccess: () => toast.success('Invite withdrawn'),
      onError: () => toast.error('Failed to withdraw invite. Please try again.'),
    });
  }

  return (
    <div className="rounded-lg border p-4" data-testid={`crossover-invite-card-${invite.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium">{eventTitle ?? `Event #${invite.event}`}</span>
            <Badge variant={STATUS_VARIANT[status] ?? 'outline'} className="capitalize">
              {status}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {isSent ? 'To story: ' : 'From GM #'}
            {isSent ? (
              <span className="font-medium">{storyTitle ?? `#${invite.to_story}`}</span>
            ) : (
              invite.from_gm
            )}
          </p>
          {invite.message && (
            <p className="mt-2 text-sm" data-testid={`invite-message-${invite.id}`}>
              {invite.message}
            </p>
          )}
          {invite.response_note && (
            <p className="mt-1 text-sm text-muted-foreground">Response: {invite.response_note}</p>
          )}
        </div>
      </div>

      {/* Actions */}
      {isPending && (
        <div className="mt-3 flex gap-2">
          {!isSent && (
            <>
              <Button
                size="sm"
                onClick={() => setAcceptOpen(true)}
                data-testid={`invite-accept-${invite.id}`}
              >
                Accept
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={handleDecline}
                disabled={declineMutation.isPending}
                data-testid={`invite-decline-${invite.id}`}
              >
                {declineMutation.isPending ? 'Declining…' : 'Decline'}
              </Button>
            </>
          )}
          {isSent && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleWithdraw}
              disabled={withdrawMutation.isPending}
              data-testid={`invite-withdraw-${invite.id}`}
            >
              {withdrawMutation.isPending ? 'Withdrawing…' : 'Withdraw'}
            </Button>
          )}
        </div>
      )}

      {!isSent && (
        <AcceptInviteDialog invite={invite} open={acceptOpen} onOpenChange={setAcceptOpen} />
      )}
    </div>
  );
}
