import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

import { useBuildingManagerQuery, useRoomBuilderAction } from '../queries';
import type { RoomBuilderActionKey } from '../types';
import { BudgetMeter } from './BudgetMeter';
import { BuilderCanvas } from './BuilderCanvas';

interface BuildingBuilderDialogProps {
  buildingId: number;
  /** The active puppet's ObjectDB pk (viewer context for reads + dispatch). */
  characterId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
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
  const [selectedRoomId, setSelectedRoomId] = useState<number | null>(null);
  const [floor, setFloor] = useState(0);
  const action = useRoomBuilderAction(characterId, buildingId);

  const payload = manager.data;
  const floors = payload?.building.floors.length ? payload.building.floors : [0];
  const selectedRoom = payload?.rooms.find((room) => room.id === selectedRoomId) ?? null;

  const runAction = (key: RoomBuilderActionKey, kwargs: Record<string, unknown>) => {
    action.mutate({ key, kwargs });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[92vh] w-[96vw] max-w-none flex-col sm:max-w-[96vw]">
        <DialogHeader className="flex-row items-center justify-between gap-4 space-y-0 pr-8">
          <DialogTitle>
            {payload ? `${payload.building.name} — ${payload.building.kind}` : 'Building manager'}
          </DialogTitle>
          <div className="flex items-center gap-4">
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
                runAction={runAction}
              />
            </div>
            <div className="w-80 shrink-0 overflow-y-auto rounded-md border p-3">
              {/* RoomDetailPanel mounts here for the selected room. */}
              <div className="text-sm text-muted-foreground">
                {selectedRoom
                  ? `${selectedRoom.name} selected.`
                  : 'Select a room on the map to edit it.'}
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
