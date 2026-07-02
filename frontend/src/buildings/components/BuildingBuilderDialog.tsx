import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

import { useBuildingManagerQuery } from '../queries';
import { BudgetMeter } from './BudgetMeter';

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

  const payload = manager.data;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[92vh] w-[96vw] max-w-none flex-col sm:max-w-[96vw]">
        <DialogHeader className="flex-row items-center justify-between gap-4 space-y-0 pr-8">
          <DialogTitle>
            {payload ? `${payload.building.name} — ${payload.building.kind}` : 'Building manager'}
          </DialogTitle>
          {payload && <BudgetMeter building={payload.building} />}
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
            <div className="min-w-0 flex-1 rounded-md border" data-testid="builder-canvas-slot">
              {/* BuilderCanvas mounts here (map, ghost-cell digs, drag placement). */}
              <div className="flex h-full items-center justify-center text-muted-foreground">
                Map canvas
              </div>
            </div>
            <div className="w-80 shrink-0 overflow-y-auto rounded-md border p-3">
              {/* RoomDetailPanel mounts here for the selected room. */}
              <div className="text-sm text-muted-foreground">
                Select a room on the map to edit it.
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
