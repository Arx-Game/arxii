/**
 * PendingInvitesSection — accept/decline incoming mission invites (#2049).
 *
 * Renders the pending_invites list from the journal payload. Invites are
 * persona-scoped (not per-instance), so they appear once at the top of the
 * journal page. Mirrors the telnet ``mission accept|decline <invite-id>``
 * surface (commands/missions.py:253).
 */
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

import { ApiValidationError, flattenErrorMessage } from '../api';
import { useRespondToMissionInvite } from '../queries';
import type { PendingMissionInvite } from '../types';

interface PendingInvitesSectionProps {
  invites: PendingMissionInvite[];
}

export function PendingInvitesSection({ invites }: PendingInvitesSectionProps) {
  const respond = useRespondToMissionInvite();

  if (invites.length === 0) return null;

  return (
    <section className="space-y-2" data-testid="pending-invites">
      <h2 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
        Invitations
      </h2>
      {invites.map((invite) => (
        <div
          key={invite.invite_id}
          className="flex items-center justify-between gap-2 rounded border p-2"
          data-testid={`invite-${invite.invite_id}`}
        >
          <div className="space-y-0.5">
            <p className="text-sm font-medium">{invite.template_name}</p>
            <Badge variant="outline">pending</Badge>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={respond.isPending}
              onClick={() => respond.mutate({ invite_id: invite.invite_id, response: 'accept' })}
              data-testid={`invite-accept-${invite.invite_id}`}
            >
              Accept
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={respond.isPending}
              onClick={() => respond.mutate({ invite_id: invite.invite_id, response: 'decline' })}
              data-testid={`invite-decline-${invite.invite_id}`}
            >
              Decline
            </Button>
          </div>
        </div>
      ))}
      {respond.error ? (
        <p className="text-xs text-destructive" data-testid="invite-respond-error">
          {respond.error instanceof ApiValidationError
            ? flattenErrorMessage(respond.error.fieldErrors)
            : respond.error.message}
        </p>
      ) : null}
    </section>
  );
}
