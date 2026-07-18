/**
 * FocusPanel — right-sidebar focus stack orchestrator.
 *
 * The right sidebar's "Room" tab is no longer hard-wired to a single view.
 * It hosts a focus stack: the room is the default (root) focus, but a
 * player can drill into a character (looking at someone) and from there
 * into an individual item. Each push appends to the stack; ``Back`` pops
 * one entry. The bottom of the stack is always preserved by
 * ``useFocusStack``, so we can render unconditionally.
 *
 * The stack itself lives in ``GamePage`` so the parent can drive the
 * sidebar tab label (which mirrors ``focus.current`` — see Task 9 spec).
 * This component is intentionally a thin renderer over the stack: it
 * decides which sub-view to show and provides the back-navigation chrome.
 */

import { useEffect, useMemo, type ReactNode } from 'react';
import { ChevronLeft } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { CharacterFocusView } from '@/inventory/components/CharacterFocusView';
import { ItemFocusView } from '@/inventory/components/ItemFocusView';
import type { FocusStackApi } from '@/inventory/hooks/useFocusStack';
import type { RoomStateObject, SceneSummary } from '@/hooks/types';
import { dbrefToId } from '@/lib/dbref';
import { useMyRosterEntriesQuery } from '@/roster/queries';

import { RoomPanel, type RoomData } from './RoomPanel';

interface FocusPanelProps {
  focus: FocusStackApi;
  /**
   * The active puppet's name (matches the redux ``active`` key). Used to
   * resolve the observer character id by looking it up in the user's
   * roster entries, which carry ``character_id``.
   */
  roomCharacter: string | null;
  roomData: RoomData | null;
  sceneData: SceneSummary | null;
  /** True when the scene's room has an active CombatEncounter (#2157). */
  hasActiveEncounter?: boolean;
  /** True when the scene's room has an active Battle (#2157). */
  hasActiveBattle?: boolean;
}

export function FocusPanel({
  focus,
  roomCharacter,
  roomData,
  sceneData,
  hasActiveEncounter = false,
  hasActiveBattle = false,
}: FocusPanelProps) {
  // Resolve the active puppet name to a numeric character id. The
  // visible-worn endpoints require an ``observer`` query parameter, and
  // the room-state ``active`` key is just the character's name. The
  // user's roster entries carry ``character_id`` (the ObjectDB pk),
  // which is the canonical id for these endpoints.
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const observerId = useMemo<number | null>(() => {
    if (!roomCharacter) {
      return null;
    }
    const match = myRosterEntries.find((entry) => entry.name === roomCharacter);
    return match?.character_id ?? null;
  }, [myRosterEntries, roomCharacter]);
  // The active puppet's RosterEntry pk — the hub wanted board's viewer scope (#1826).
  const viewerEntryId = useMemo<number | null>(() => {
    if (!roomCharacter) {
      return null;
    }
    const match = myRosterEntries.find((entry) => entry.name === roomCharacter);
    return match?.id ?? null;
  }, [myRosterEntries, roomCharacter]);

  // When the underlying room, scene, or active puppet changes (player
  // switches puppets, moves rooms, or starts/ends a scene), reset the
  // focus stack so the sidebar snaps back to the new room as its root.
  // We key this on the room id, scene id, and active puppet name rather
  // than object identity to avoid resetting on every redux dispatch
  // that happens to recreate the object. ``roomCharacter`` is included
  // because two characters can share a room — without it, swapping
  // puppets in the same room would leak the previous puppet's focus
  // stack to the new puppet's session.
  const roomId = roomData?.id ?? null;
  const sceneId = sceneData?.id ?? null;
  const { reset } = focus;
  useEffect(() => {
    if (!roomData) {
      return;
    }
    reset({
      kind: 'room',
      room: {
        dbref: `#${roomData.id}`,
        name: roomData.name,
        thumbnail_url: roomData.thumbnail_url,
        commands: [],
        description: roomData.description,
      },
      sceneSummary: sceneData,
    });
    // ``reset`` is referentially stable from useFocusStack, so depending
    // on the room/scene identifiers + active puppet is sufficient. We
    // intentionally exclude ``roomData``/``sceneData`` themselves to
    // avoid resetting on every redux re-render that recreates the
    // object reference.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomCharacter, roomId, sceneId, reset]);

  const showBack = focus.depth > 1;

  const onCharacterClickFromRoom = (character: RoomStateObject) => {
    focus.push({
      kind: 'character',
      character: { id: dbrefToId(character.dbref), name: character.name },
    });
  };

  let body: ReactNode;
  switch (focus.current.kind) {
    case 'room':
      body = (
        <RoomPanel
          character={roomCharacter}
          characterId={observerId}
          room={roomData}
          scene={sceneData}
          onCharacterClick={onCharacterClickFromRoom}
          hasActiveEncounter={hasActiveEncounter}
          hasActiveBattle={hasActiveBattle}
          viewerEntryId={viewerEntryId}
        />
      );
      break;
    case 'character':
      body = (
        <CharacterFocusView
          character={focus.current.character}
          observerId={observerId}
          onItemClick={(item) => focus.push({ kind: 'item', item })}
        />
      );
      break;
    case 'item':
      body = (
        <ItemFocusView
          item={focus.current.item}
          observerId={observerId}
          character={roomCharacter}
          onStolen={focus.pop}
        />
      );
      break;
  }

  return (
    <div className="flex h-full flex-col">
      {showBack && (
        <div className="border-b px-2 py-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={focus.pop}
            className="gap-1 text-xs"
            data-testid="focus-back-button"
          >
            <ChevronLeft className="h-3 w-3" />
            Back
          </Button>
        </div>
      )}
      <div className="flex-1 overflow-y-auto">{body}</div>
    </div>
  );
}
