/**
 * StoryBuilderPage — `/gm/story-builder` (#2450): left rail is the GM's own
 * story areas + temp scene rooms, center is a canvas over the selected
 * area's manager payload (reusing world-builder's
 * `WorldCanvas`/`DigRoomDialog`/`LinkRoomsDialog`/`RoomDetailPanel` with
 * `palette="story"` — see those components' doc comments for exactly what
 * the story palette hides/renames), right is the selected room's detail
 * panel plus its access-grant list.
 *
 * Structurally mirrors `WorldBuilderPage`
 * (`@/world-builder/pages/WorldBuilderPage`) — the GM-owned character-id
 * resolution is identical (see that page's module doc): dispatch still
 * needs a `characterId` even though story-builder actions are gated on GM
 * trust rather than staff, because `Action.run(actor=<puppet>)` always needs
 * an acting ObjectDB.
 *
 * `StoryAreaListPanel`/`CreateStoryAreaDialog`/`TempRoomsPanel`/
 * `RoomAccessPanel` are story-builder-only (not shared with world-builder) —
 * see `StoryAreaListPanel`'s doc comment for why a GM's flat, non-nested
 * story areas don't fit `AreaTreePanel`'s recursive-tree shape or its
 * hardwired staff data source.
 */
import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { GhostCell } from '@/map-canvas/ghosts';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useAppSelector } from '@/store/hooks';
import { DigRoomDialog } from '@/world-builder/components/DigRoomDialog';
import { LinkRoomsDialog } from '@/world-builder/components/LinkRoomsDialog';
import { RoomDetailPanel } from '@/world-builder/components/RoomDetailPanel';
import { WorldCanvas } from '@/world-builder/components/WorldCanvas';

import { CreateStoryAreaDialog } from '../components/CreateStoryAreaDialog';
import { RoomAccessPanel } from '../components/RoomAccessPanel';
import { StoryAreaListPanel } from '../components/StoryAreaListPanel';
import { TempRoomsPanel } from '../components/TempRoomsPanel';
import { useStoryAreaManagerQuery, useStoryBuilderAction } from '../queries';
import type { StoryBuilderActionKey } from '../types';

export function StoryBuilderPage() {
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((entry) => entry.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );

  const [selectedAreaId, setSelectedAreaId] = useState<number | null>(null);
  const [selectedRoomId, setSelectedRoomId] = useState<number | null>(null);
  const [floor, setFloor] = useState(0);
  const [createAreaOpen, setCreateAreaOpen] = useState(false);
  const [digPrefill, setDigPrefill] = useState<{ grid_x: number; grid_y: number } | undefined>();
  const [digOpen, setDigOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);

  const { data: manager, isLoading } = useStoryAreaManagerQuery(selectedAreaId);
  const { mutate: runMutation } = useStoryBuilderAction(characterId ?? 0, selectedAreaId);

  // Keyed generically (not `StoryBuilderActionKey`) so this callback
  // satisfies the shared world-builder canvas/dialog/panel components'
  // widened `runAction` prop type (#2450); the cast back at the mutation
  // boundary keeps `useStoryBuilderAction` itself narrowly typed.
  const runAction = (key: string, kwargs: Record<string, unknown>) => {
    if (characterId == null) return;
    runMutation({ key: key as StoryBuilderActionKey, kwargs });
  };

  // Grant/revoke need a per-call success callback (to update
  // `RoomAccessPanel`'s client-tracked "granted this session" list — see its
  // doc comment for why there's no server list to read back instead), so
  // this is a separate mutate call from the generic `runAction` above rather
  // than threading an `onSuccess` param through every action's kwargs.
  const runAccessAction = (
    key: 'grant_story_room' | 'revoke_story_room',
    kwargs: Record<string, unknown>,
    onSuccess: () => void
  ) => {
    if (characterId == null) return;
    runMutation(
      { key, kwargs },
      {
        onSuccess: (result) => {
          if (result.success !== false) onSuccess();
        },
      }
    );
  };

  const selectedRoom = manager?.rooms.find((room) => room.id === selectedRoomId) ?? null;

  const floors = useMemo(() => {
    const set = new Set((manager?.rooms ?? []).map((room) => room.floor));
    set.add(0);
    return [...set].sort((a, b) => a - b);
  }, [manager]);

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col gap-2 p-2" data-testid="story-builder-page">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Story Builder</h1>
        {manager && (
          <Select value={String(floor)} onValueChange={(value) => setFloor(Number(value))}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {floors.map((f) => (
                <SelectItem key={f} value={String(f)}>
                  Floor {f}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>
      <div className="grid flex-1 grid-cols-[240px_1fr_320px] gap-2 overflow-hidden">
        <Card className="flex flex-col overflow-hidden">
          <StoryAreaListPanel
            selectedAreaId={selectedAreaId}
            onSelectArea={(id) => {
              setSelectedAreaId(id);
              setSelectedRoomId(null);
            }}
            onCreateArea={() => setCreateAreaOpen(true)}
            runAction={runAction}
          />
          <TempRoomsPanel runAction={runAction} runAccessAction={runAccessAction} />
        </Card>
        <Card className="overflow-hidden">
          <CardContent className="flex h-full flex-col gap-2 p-2">
            {!selectedAreaId && (
              <p className="text-sm text-muted-foreground">Pick a story area to see its map.</p>
            )}
            {selectedAreaId && isLoading && (
              <p className="text-sm text-muted-foreground">Loading…</p>
            )}
            {selectedAreaId && manager && (
              <>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="self-start"
                  onClick={() => {
                    setDigPrefill(undefined);
                    setDigOpen(true);
                  }}
                >
                  Dig room
                </Button>
                <div className="flex-1">
                  <WorldCanvas
                    payload={manager}
                    floor={floor}
                    selectedRoomId={selectedRoomId}
                    onSelectRoom={setSelectedRoomId}
                    onDigAt={(ghost: GhostCell) => {
                      setDigPrefill({ grid_x: ghost.x, grid_y: ghost.y });
                      setDigOpen(true);
                    }}
                    runAction={runAction}
                    palette="story"
                  />
                </div>
              </>
            )}
          </CardContent>
        </Card>
        <Card className="overflow-y-auto">
          <CardContent className="flex flex-col gap-3 p-3">
            {selectedRoom ? (
              <>
                <RoomDetailPanel
                  room={selectedRoom}
                  exits={manager?.exits ?? []}
                  runAction={runAction}
                  onLinkRooms={() => setLinkOpen(true)}
                  palette="story"
                />
                <RoomAccessPanel roomId={selectedRoom.id} runAccessAction={runAccessAction} />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Pick a room to edit it.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <CreateStoryAreaDialog
        open={createAreaOpen}
        onOpenChange={setCreateAreaOpen}
        runAction={runAction}
      />

      {selectedAreaId != null && (
        <DigRoomDialog
          areaId={selectedAreaId}
          floor={floor}
          prefill={digPrefill}
          open={digOpen}
          onOpenChange={(open) => {
            setDigOpen(open);
            if (!open) setDigPrefill(undefined);
          }}
          runAction={runAction}
          palette="story"
        />
      )}

      {selectedRoom && (
        <LinkRoomsDialog
          fromRoom={selectedRoom}
          sameAreaRooms={(manager?.rooms ?? []).filter((room) => room.id !== selectedRoom.id)}
          open={linkOpen}
          onOpenChange={setLinkOpen}
          runAction={runAction}
          palette="story"
        />
      )}
    </div>
  );
}
