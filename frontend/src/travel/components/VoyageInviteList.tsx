/**
 * VoyageInviteList — inbox of pending voyage invitations (#2352).
 *
 * Shows PENDING VoyageInvites targeting the active character with
 * Accept/Decline buttons.
 */

import { usePendingVoyageInvites, useRespondVoyageInvite } from '../queries';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

interface VoyageInviteListProps {
  characterId: number;
}

export function VoyageInviteList({ characterId }: VoyageInviteListProps) {
  const { data: invites, isLoading } = usePendingVoyageInvites();
  const respond = useRespondVoyageInvite(characterId);

  if (isLoading) {
    return <p className="p-3 text-sm text-muted-foreground">Loading invites…</p>;
  }

  if (!invites || invites.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold text-muted-foreground">Voyage Invitations</h3>
      {invites.map((invite) => (
        <Card key={invite.id} className="border p-2 text-xs">
          <div className="font-medium">Voyage to {invite.voyage_destination}</div>
          <div className="text-muted-foreground">
            Invited by {invite.invited_by_name ?? 'Unknown'}
          </div>
          <div className="mt-2 flex gap-2">
            <Button
              size="sm"
              variant="default"
              className="h-6 text-xs"
              disabled={respond.isPending}
              onClick={() => respond.mutate({ invite_id: invite.id, accept: true })}
            >
              Accept
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-6 text-xs"
              disabled={respond.isPending}
              onClick={() => respond.mutate({ invite_id: invite.id, accept: false })}
            >
              Decline
            </Button>
          </div>
        </Card>
      ))}
    </div>
  );
}
