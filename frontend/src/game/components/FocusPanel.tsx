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

import { useEffect, type ReactNode } from 'react';
import { ChevronLeft } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { CharacterFocusView } from '@/inventory/components/CharacterFocusView';
import { ItemFocusView } from '@/inventory/components/ItemFocusView';
import type { FocusStackApi } from '@/inventory/hooks/useFocusStack';
import type { RoomStateObject, SceneSummary } from '@/hooks/types';

import { RoomPanel, type RoomData } from './RoomPanel';

interface FocusPanelProps {
  focus: FocusStackApi;
  roomCharacter: string | null;
  roomData: RoomData | null;
  sceneData: SceneSummary | null;
}

/**
 * Convert an Evennia dbref like ``#42`` to the numeric id used by REST
 * endpoints. Falls back to ``0`` when parsing fails — the backing
 * detail/list endpoints will return 404 for a bogus id, which the focus
 * views render as their unavailable state. Better than throwing inside
 * a click handler.
 */
function dbrefToId(dbref: string): number {
  const stripped = dbref.startsWith('#') ? dbref.slice(1) : dbref;
  const parsed = Number.parseInt(stripped, 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function FocusPanel({ focus, roomCharacter, roomData, sceneData }: FocusPanelProps) {
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
          room={roomData}
          scene={sceneData}
          onCharacterClick={onCharacterClickFromRoom}
        />
      );
      break;
    case 'character':
      body = (
        <CharacterFocusView
          character={focus.current.character}
          onItemClick={(item) => focus.push({ kind: 'item', item })}
        />
      );
      break;
    case 'item':
      body = <ItemFocusView item={focus.current.item} />;
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
