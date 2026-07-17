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
import type { GhostCell } from '@/buildings/gridMath';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useAppSelector } from '@/store/hooks';

import { AreaTreePanel } from '../components/AreaTreePanel';
import { CreateAreaDialog } from '../components/CreateAreaDialog';
import { DigRoomDialog } from '../components/DigRoomDialog';
import { LinkRoomsDialog } from '../components/LinkRoomsDialog';
import { RoomDetailPanel } from '../components/RoomDetailPanel';
import { WorldCanvas } from '../components/WorldCanvas';
import { useAreaManagerQuery, useWorldBuilderAction } from '../queries';
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
  const [digPrefill, setDigPrefill] = useState<{ grid_x: number; grid_y: number } | undefined>();
  const [digOpen, setDigOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);

  const { data: manager, isLoading } = useAreaManagerQuery(selectedAreaId);
  const { mutate: runMutation } = useWorldBuilderAction(characterId ?? 0, selectedAreaId);

  const runAction = (key: WorldBuilderActionKey, kwargs: Record<string, unknown>) => {
    if (characterId == null) return;
    runMutation({ key, kwargs });
  };

  const selectedRoom = manager?.rooms.find((room) => room.id === selectedRoomId) ?? null;

  const floors = useMemo(() => {
    const set = new Set((manager?.rooms ?? []).map((room) => room.floor));
    set.add(0);
    return [...set].sort((a, b) => a - b);
  }, [manager]);

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col gap-2 p-2" data-testid="world-builder-page">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">World Builder</h1>
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
                  />
                </div>
              </>
            )}
          </CardContent>
        </Card>
        <Card className="overflow-y-auto">
          <CardContent className="p-3">
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
          prefill={digPrefill}
          open={digOpen}
          onOpenChange={(open) => {
            setDigOpen(open);
            if (!open) setDigPrefill(undefined);
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
