/**
 * WorldBuilderPage — `/staff/world-builder` (#2449): left area tree, center
 * canvas over the selected area's manager payload, right room detail panel.
 *
 * Even a staff-only REGISTRY action runs through `action.run(actor=<puppet>)`
 * (see `src/actions/definitions/world_builder.py`'s module docstring), so
 * dispatch still needs a `characterId` — resolved the same way as
 * `StagingPanel` (`frontend/src/battles/components/StagingPanel.tsx:80-88`):
 * the active character's name from Redux, matched against the account's
 * roster entries for its `character_id`.
 */
import { useEffect, useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
import { toast } from 'sonner';

import { AreaTreePanel } from '../components/AreaTreePanel';
import { CreateAreaDialog } from '../components/CreateAreaDialog';
import { DigRoomDialog } from '../components/DigRoomDialog';
import { LinkRoomsDialog } from '../components/LinkRoomsDialog';
import { PromoteAreaButton } from '../components/PromoteAreaButton';
import { RoomDetailPanel } from '../components/RoomDetailPanel';
import { WorldCanvas } from '../components/WorldCanvas';
import { useAreaManagerQuery, useRoomSearchQuery, useWorldBuilderAction } from '../queries';
import type { WorldBuilderActionKey } from '../types';

export function WorldBuilderPage() {
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((entry) => entry.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );

  const [selectedAreaId, setSelectedAreaId] = useState<number | null>(null);
  const [selectedRoomId, setSelectedRoomId] = useState<number | null>(null);
  const [floor, setFloor] = useState(0);
  const [createAreaParent, setCreateAreaParent] = useState<number | null | undefined>(undefined);
  const [digPrefill, setDigPrefill] = useState<
    { grid_x: number; grid_y: number; fromRoomId?: number; direction?: string } | undefined
  >();
  const [digFromName, setDigFromName] = useState<string | undefined>();
  const [digOpen, setDigOpen] = useState(false);
  // #3269 place-mode: an unplaced room awaiting a ghost-cell click.
  const [placeModeRoomId, setPlaceModeRoomId] = useState<number | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const { data: roomHits } = useRoomSearchQuery(searchTerm);
  const [linkOpen, setLinkOpen] = useState(false);

  const { data: manager, isLoading } = useAreaManagerQuery(selectedAreaId);
  const { mutate: runMutation } = useWorldBuilderAction(characterId ?? 0, selectedAreaId);

  // Keyed generically (not `WorldBuilderActionKey`) so this callback still
  // satisfies the shared canvas/dialog/panel components' widened `runAction`
  // prop type (they also serve the story palette's own key union, #2450);
  // the cast back to `WorldBuilderActionKey` at the mutation boundary keeps
  // `useWorldBuilderAction` itself narrowly typed for this page's own calls.
  const runAction = (key: string, kwargs: Record<string, unknown>) => {
    if (characterId == null) {
      // #3269 — the old silent return made the whole tool a dead console.
      toast.error(
        'Select a character to build as; builder actions dispatch through your played character.'
      );
      return;
    }
    runMutation({ key: key as WorldBuilderActionKey, kwargs });
  };

  // Esc cancels place-mode (#3269).
  useEffect(() => {
    if (placeModeRoomId == null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPlaceModeRoomId(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [placeModeRoomId]);

  const selectedRoom = manager?.rooms.find((room) => room.id === selectedRoomId) ?? null;
  const unplacedRooms = (manager?.rooms ?? []).filter(
    (room) => room.grid_x === null || room.grid_y === null
  );
  const needsProseRooms = (manager?.rooms ?? []).filter((room) => room.needs_prose);

  const floors = useMemo(() => {
    const set = new Set((manager?.rooms ?? []).map((room) => room.floor));
    set.add(0);
    return [...set].sort((a, b) => a - b);
  }, [manager]);

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col gap-2 p-2" data-testid="world-builder-page">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold">World Builder</h1>
          {manager && <PromoteAreaButton area={manager.area} runAction={runAction} />}
        </div>
        <div className="relative">
          <Input
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Find a room anywhere..."
            className="w-64"
            data-testid="room-search-input"
          />
          {searchTerm.trim().length >= 2 && (roomHits?.length ?? 0) > 0 && (
            <div className="absolute z-20 mt-1 max-h-64 w-80 overflow-y-auto rounded border bg-popover p-1 shadow">
              {roomHits!.map((hit) => (
                <button
                  key={hit.id}
                  type="button"
                  className="block w-full rounded px-2 py-1 text-left text-sm hover:bg-accent"
                  onClick={() => {
                    if (hit.area_id != null) setSelectedAreaId(hit.area_id);
                    setFloor(hit.floor);
                    setSelectedRoomId(hit.id);
                    setSearchTerm('');
                  }}
                >
                  <span className="font-medium">{hit.name}</span>{' '}
                  <span className="text-muted-foreground">
                    {hit.area_name ?? 'no area'} - floor {hit.floor}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
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
      {characterId == null && (
        <div
          className="rounded border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm"
          data-testid="world-builder-actor-banner"
        >
          Select a character to build as - builder actions dispatch through your played character,
          so every control is inert until you are playing one.
        </div>
      )}
      {placeModeRoomId != null && (
        <div
          className="rounded border border-sky-500/50 bg-sky-500/10 px-3 py-2 text-sm"
          data-testid="world-builder-place-banner"
        >
          Placing: {manager?.rooms.find((room) => room.id === placeModeRoomId)?.name} - click a
          highlighted cell, or press Esc to cancel.
        </div>
      )}
      <div className="grid flex-1 grid-cols-[240px_1fr_320px] gap-2 overflow-hidden">
        <Card className="overflow-hidden">
          <AreaTreePanel
            selectedAreaId={selectedAreaId}
            onSelectArea={(id) => {
              setSelectedAreaId(id);
              setSelectedRoomId(null);
            }}
            onCreateArea={(parentId) => setCreateAreaParent(parentId)}
          />
        </Card>
        <Card className="overflow-hidden">
          <CardContent className="flex h-full flex-col gap-2 p-2">
            {!selectedAreaId && (
              <p className="text-sm text-muted-foreground">Pick an area to see its map.</p>
            )}
            {selectedAreaId && isLoading && (
              <p className="text-sm text-muted-foreground">Loading…</p>
            )}
            {selectedAreaId && manager && manager.rooms.length === 0 && (
              <div
                className="flex h-full flex-col items-center justify-center gap-3"
                data-testid="dig-first-room-empty-state"
              >
                <p className="text-sm text-muted-foreground">
                  This area has no rooms yet. The first room lands at the grid origin; dig neighbors
                  off it from there.
                </p>
                <Button
                  type="button"
                  onClick={() => {
                    setDigFromName(undefined);
                    setDigPrefill({ grid_x: 0, grid_y: 0 });
                    setDigOpen(true);
                  }}
                >
                  Dig first room
                </Button>
              </div>
            )}
            {selectedAreaId && manager && manager.rooms.length > 0 && (
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
                      if (placeModeRoomId != null) {
                        runAction('staff_place_room', {
                          room_id: placeModeRoomId,
                          grid_x: ghost.x,
                          grid_y: ghost.y,
                          floor,
                        });
                        setPlaceModeRoomId(null);
                        return;
                      }
                      const anchor = manager.rooms.find((room) => room.id === ghost.fromRoomId);
                      setDigFromName(anchor?.name);
                      setDigPrefill({
                        grid_x: ghost.x,
                        grid_y: ghost.y,
                        fromRoomId: ghost.fromRoomId,
                        direction: ghost.direction,
                      });
                      setDigOpen(true);
                    }}
                    runAction={runAction}
                  />
                </div>
              </>
            )}
          </CardContent>
        </Card>
        <Card className="overflow-y-auto">
          <CardContent className="flex flex-col gap-3 p-3">
            {unplacedRooms.length > 0 && (
              <div data-testid="unplaced-rooms-list">
                <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                  Unplaced rooms ({unplacedRooms.length})
                </p>
                <div className="flex flex-col gap-1">
                  {unplacedRooms.map((room) => (
                    <button
                      key={room.id}
                      type="button"
                      className="rounded border px-2 py-1 text-left text-sm hover:bg-accent"
                      onClick={() => {
                        setSelectedRoomId(room.id);
                        setPlaceModeRoomId(room.id);
                      }}
                    >
                      {room.name}{' '}
                      <span className="text-xs text-muted-foreground">click to place</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {needsProseRooms.length > 0 && (
              <div data-testid="needs-prose-list">
                <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                  Needs prose ({needsProseRooms.length})
                </p>
                <div className="flex flex-col gap-1">
                  {needsProseRooms.map((room) => (
                    <button
                      key={room.id}
                      type="button"
                      className="rounded px-2 py-0.5 text-left text-sm text-muted-foreground hover:bg-accent"
                      onClick={() => setSelectedRoomId(room.id)}
                    >
                      {room.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {selectedRoom ? (
              <RoomDetailPanel
                room={selectedRoom}
                exits={manager?.exits ?? []}
                runAction={runAction}
                onLinkRooms={() => setLinkOpen(true)}
              />
            ) : (
              <p className="text-sm text-muted-foreground">Pick a room to edit it.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {createAreaParent !== undefined && (
        <CreateAreaDialog
          parentId={createAreaParent}
          open={createAreaParent !== undefined}
          onOpenChange={(open) => {
            if (!open) setCreateAreaParent(undefined);
          }}
          runAction={runAction}
        />
      )}

      {selectedAreaId != null && (
        <DigRoomDialog
          areaId={selectedAreaId}
          floor={floor}
          areaBreadcrumb={
            manager ? `${manager.area.name} (${manager.area.level_display})` : undefined
          }
          fromRoomName={digFromName}
          prefill={digPrefill}
          open={digOpen}
          onOpenChange={(open) => {
            setDigOpen(open);
            if (!open) {
              setDigPrefill(undefined);
              setDigFromName(undefined);
            }
          }}
          runAction={runAction}
        />
      )}

      {selectedRoom && (
        <LinkRoomsDialog
          fromRoom={selectedRoom}
          sameAreaRooms={(manager?.rooms ?? []).filter((room) => room.id !== selectedRoom.id)}
          open={linkOpen}
          onOpenChange={setLinkOpen}
          runAction={runAction}
        />
      )}
    </div>
  );
}
