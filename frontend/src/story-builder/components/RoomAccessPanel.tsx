/**
 * RoomAccessPanel — grant/revoke a character's access to a story-area room
 * or temp scene room (#2450), via the `grant_story_room`/`revoke_story_room`
 * actions (`_resolve_owned_story_or_temp_room` on the backend accepts either
 * kind of room id, so this one panel serves both `RoomDetailPanel` and
 * `TempRoomsPanel`'s per-row access list).
 *
 * Fix round 1 (#2450 Task 10 follow-up): the grant list is now server-backed
 * — `grants` comes straight from the parent's already-fetched manager/
 * instances payload (`world.gm.story_views` batch-attaches
 * `StoryRoomGrant` names, see `_grants_by_room`), so it survives a reload and
 * reflects grants made in any session, not just this one. This panel is
 * purely a form + list over that prop; it holds no grant state of its own.
 */
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export interface RoomAccessPanelProps {
  roomId: number;
  grants: string[];
  runAccessAction: (
    key: 'grant_story_room' | 'revoke_story_room',
    kwargs: Record<string, unknown>,
    onSuccess: () => void
  ) => void;
}

export function RoomAccessPanel({ roomId, grants, runAccessAction }: RoomAccessPanelProps) {
  const [characterName, setCharacterName] = useState('');

  const grant = () => {
    const trimmed = characterName.trim();
    if (!trimmed) return;
    runAccessAction('grant_story_room', { room_id: roomId, character_name: trimmed }, () => {
      setCharacterName('');
    });
  };

  const revoke = (grantedName: string) => {
    runAccessAction(
      'revoke_story_room',
      { room_id: roomId, character_name: grantedName },
      () => {}
    );
  };

  return (
    <div className="flex flex-col gap-2 rounded-md border p-2" data-testid="room-access-panel">
      <h4 className="text-sm font-semibold">Access</h4>
      <div className="flex items-center gap-1.5">
        <Input
          value={characterName}
          onChange={(event) => setCharacterName(event.target.value)}
          placeholder="Character name"
          className="h-8 flex-1"
          data-testid="room-access-name-input"
        />
        <Button size="sm" onClick={grant} disabled={!characterName.trim()}>
          Grant
        </Button>
      </div>
      {grants.length === 0 ? (
        <p className="text-xs text-muted-foreground">No one has access yet.</p>
      ) : (
        grants.map((grantedName) => (
          <div key={grantedName} className="flex items-center justify-between gap-1.5">
            <span className="text-sm">{grantedName}</span>
            <Button variant="ghost" size="sm" onClick={() => revoke(grantedName)}>
              Revoke
            </Button>
          </div>
        ))
      )}
    </div>
  );
}
