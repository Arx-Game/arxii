/**
 * InvitePicker — invite a co-located character to a mission run (#2049).
 *
 * Contract-holder-only affordance. Uses the reusable EntitySearchField with
 * searchRoomCharacters (the room-occupant search endpoint) to pick a character,
 * then dispatches inviteToMission. Mirrors the TriggerGiversPage target picker
 * pattern (#882).
 */
import { useState } from 'react';

import { EntitySearchField } from '@/components/EntitySearchField';
import { Button } from '@/components/ui/button';

import { ApiValidationError, flattenErrorMessage, searchRoomCharacters } from '../api';
import { useInviteToMission } from '../queries';

interface InvitePickerProps {
  instanceId: number;
}

export function InvitePicker({ instanceId }: InvitePickerProps) {
  const [target, setTarget] = useState<number | null>(null);
  const invite = useInviteToMission();

  return (
    <div className="space-y-2" data-testid="invite-picker">
      <EntitySearchField
        value={target}
        onChange={setTarget}
        search={(q) => searchRoomCharacters(q)}
        label="Invite a companion"
        placeholder="Search characters in this room…"
      />
      <Button
        size="sm"
        variant="outline"
        disabled={target === null || invite.isPending}
        onClick={() => {
          if (target === null) return;
          invite.mutate(
            { instanceId, invitee_character_id: target },
            {
              onSuccess: () => {
                setTarget(null);
              },
            }
          );
        }}
        data-testid="invite-submit"
      >
        {invite.isPending ? 'Sending…' : 'Send invite'}
      </Button>
      {invite.error ? (
        <p className="text-xs text-destructive" data-testid="invite-error">
          {invite.error instanceof ApiValidationError
            ? flattenErrorMessage(invite.error.fieldErrors)
            : invite.error.message}
        </p>
      ) : null}
      {invite.isSuccess && !invite.isPending ? (
        <p className="text-xs text-muted-foreground" data-testid="invite-sent">
          Invite sent.
        </p>
      ) : null}
    </div>
  );
}
