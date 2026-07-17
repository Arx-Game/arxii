import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import type { GhostCell } from '@/map-canvas/ghosts';

import { useBuildingManagerQuery, useRoomBuilderAction, useRoomSizeTiersQuery } from '../queries';
import type { RoomBuilderActionKey } from '../types';
import { BudgetMeter } from './BudgetMeter';
import { BuilderCanvas } from './BuilderCanvas';
import { DecorationDialog } from './DecorationDialog';
import { DigDialog } from './DigDialog';
import { ExtensionDialog } from './ExtensionDialog';
import { RenovationDialog } from './RenovationDialog';
import { RoomDetailPanel } from './RoomDetailPanel';
import { StyleDialog } from './StyleDialog';

interface BuildingBuilderDialogProps {
  buildingId: number;
  /** The active puppet's ObjectDB pk (viewer context for reads + dispatch). */
  characterId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface DigRequest {
  fromRoomId: number;
  direction?: string;
  like?: string;
}

/**
 * The owner's building manager (#670): full-screen dialog hosting the map
 * canvas and the room detail panel. Mounted from RoomPanel so the game
 * websocket session stays alive underneath.
 */
export function BuildingBuilderDialog({
  buildingId,
  characterId,
  open,
  onOpenChange,
}: BuildingBuilderDialogProps) {
  const manager = useBuildingManagerQuery(open ? buildingId : null, characterId);
  const sizeTiers = useRoomSizeTiersQuery(open);
  const [selectedRoomId, setSelectedRoomId] = useState<number | null>(null);
  const [floor, setFloor] = useState(0);
  const [digRequest, setDigRequest] = useState<DigRequest | null>(null);
  const [decorateRoom, setDecorateRoom] = useState(false);
  const [decorateOpen, setDecorateOpen] = useState(false);
  const [extendOpen, setExtendOpen] = useState(false);
  const [renovateOpen, setRenovateOpen] = useState(false);
  const [styleOpen, setStyleOpen] = useState(false);
  const action = useRoomBuilderAction(characterId, buildingId);

  const payload = manager.data;
  const floors = payload?.building.floors.length ? payload.building.floors : [0];
  const selectedRoom = payload?.rooms.find((room) => room.id === selectedRoomId) ?? null;
  const digFromRoom = payload?.rooms.find((room) => room.id === digRequest?.fromRoomId) ?? null;
  const entryRoomId = payload?.building.entry_room_id ?? null;
  const tiers = sizeTiers.data?.results ?? [];

  const runAction = (key: RoomBuilderActionKey, kwargs: Record<string, unknown>) => {
    action.mutate({ key, kwargs });
  };

  const onDigAt = (ghost: GhostCell) => {
    setDigRequest({ fromRoomId: ghost.fromRoomId, direction: ghost.direction });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[92vh] w-[96vw] max-w-none flex-col sm:max-w-[96vw]">
        <DialogHeader className="flex-row flex-wrap items-center justify-between gap-4 space-y-0 pr-8">
          <DialogTitle>
            {payload ? `${payload.building.name} — ${payload.building.kind}` : 'Building manager'}
          </DialogTitle>
          <div className="flex flex-wrap items-center gap-3">
            {floors.length > 1 && (
              <div className="flex items-center gap-1">
                {floors.map((level) => (
                  <Button
                    key={level}
                    size="sm"
                    variant={level === floor ? 'default' : 'outline'}
                    onClick={() => setFloor(level)}
                  >
                    Floor {level}
                  </Button>
                ))}
              </div>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setDecorateRoom(false);
                setDecorateOpen(true);
              }}
              disabled={entryRoomId == null}
            >
              Decorate Building
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setExtendOpen(true)}
              disabled={entryRoomId == null}
            >
              Extend Building
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setRenovateOpen(true)}
              disabled={entryRoomId == null}
            >
              Renovate
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setStyleOpen(true)}
              disabled={entryRoomId == null}
            >
              Style
            </Button>
            {payload && <BudgetMeter building={payload.building} />}
          </div>
        </DialogHeader>
        {manager.isLoading && (
          <div className="flex flex-1 items-center justify-center text-muted-foreground">
            Loading building…
          </div>
        )}
        {manager.isError && (
          <div className="flex flex-1 items-center justify-center text-destructive">
            {(manager.error as Error).message}
          </div>
        )}
        {payload && (
          <div className="flex min-h-0 flex-1 gap-4">
            <div className="min-w-0 flex-1 rounded-md border">
              <BuilderCanvas
                payload={payload}
                floor={floor}
                selectedRoomId={selectedRoomId}
                onSelectRoom={setSelectedRoomId}
                onDigAt={onDigAt}
                onExitClick={(edge) => setSelectedRoomId(edge.source)}
                runAction={runAction}
              />
            </div>
            <div className="w-80 shrink-0 overflow-y-auto rounded-md border p-3">
              {selectedRoom ? (
                <RoomDetailPanel
                  room={selectedRoom}
                  characterId={characterId}
                  rooms={payload.rooms}
                  exits={payload.exits}
                  sizeTiers={tiers}
                  isEntry={selectedRoom.id === entryRoomId}
                  runAction={runAction}
                  onDigFrom={() => setDigRequest({ fromRoomId: selectedRoom.id })}
                  onDuplicate={() =>
                    setDigRequest({ fromRoomId: selectedRoom.id, like: selectedRoom.name })
                  }
                  onDecorateRoom={() => {
                    setDecorateRoom(true);
                    setDecorateOpen(true);
                  }}
                />
              ) : (
                <div className="text-sm text-muted-foreground">
                  Select a room on the map to edit it, click a + cell to dig, or drag rooms to
                  rearrange the map.
                </div>
              )}
            </div>
          </div>
        )}
        {digFromRoom && (
          <DigDialog
            fromRoom={digFromRoom}
            direction={digRequest?.direction}
            like={digRequest?.like}
            sizeTiers={tiers}
            open={digRequest != null}
            onOpenChange={(dialogOpen) => {
              if (!dialogOpen) setDigRequest(null);
            }}
            runAction={runAction}
          />
        )}
        {payload && entryRoomId != null && (
          <>
            <DecorationDialog
              targetRoom={decorateRoom ? selectedRoom : null}
              anchorRoomId={decorateRoom && selectedRoom ? selectedRoom.id : entryRoomId}
              open={decorateOpen}
              onOpenChange={setDecorateOpen}
              runAction={runAction}
            />
            <ExtensionDialog
              anchorRoomId={entryRoomId}
              currentBudget={payload.building.space_budget}
              open={extendOpen}
              onOpenChange={setExtendOpen}
              runAction={runAction}
            />
            <RenovationDialog
              anchorRoomId={entryRoomId}
              currentKind={payload.building.kind}
              renovationCost={payload.building.renovation_cost ?? null}
              open={renovateOpen}
              onOpenChange={setRenovateOpen}
              runAction={runAction}
            />
            <StyleDialog
              anchorRoomId={entryRoomId}
              characterId={characterId}
              currentStyle={payload.building.style ?? null}
              open={styleOpen}
              onOpenChange={setStyleOpen}
              runAction={runAction}
            />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
