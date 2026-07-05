import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

import { useBuildingKindsQuery } from '../queries';
import type { BuildingKind, RoomBuilderActionKey } from '../types';

interface RenovationDialogProps {
  /** The entry room of the building (dispatch anchor). */
  anchorRoomId: number;
  /** The building's current kind name — excluded from the renovation list. */
  currentKind: string;
  /** The server-provided renovation cost in coppers (from the manager payload). */
  renovationCost: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runAction: (key: RoomBuilderActionKey, kwargs: Record<string, unknown>) => void;
}

const KIND_FLAGS: { field: keyof BuildingKind; label: string }[] = [
  { field: 'is_residential', label: 'Residential' },
  { field: 'is_commercial', label: 'Commercial' },
  { field: 'is_fortified', label: 'Fortified' },
  { field: 'is_occult', label: 'Occult' },
  { field: 'is_maritime', label: 'Maritime' },
  { field: 'is_agrarian', label: 'Agrarian' },
  { field: 'is_aerial', label: 'Aerial' },
  { field: 'is_subterranean', label: 'Subterranean' },
  { field: 'is_secret', label: 'Secret' },
];

/**
 * Pick a new BuildingKind to renovate the building into. Mirrors
 * DecorationDialog (catalog picker → runAction). The current kind is excluded
 * client-side (the manager payload carries it).
 */
export function RenovationDialog({
  anchorRoomId,
  currentKind,
  renovationCost,
  open,
  onOpenChange,
  runAction,
}: RenovationDialogProps) {
  const kinds = useBuildingKindsQuery('', open);
  const available = (kinds.data?.results ?? []).filter((kind) => kind.name !== currentKind);

  const renovate = (kindName: string) => {
    runAction('start_building_renovation', { room_id: anchorRoomId, target_kind: kindName });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Renovate the building</DialogTitle>
        </DialogHeader>
        {renovationCost != null && (
          <p className="text-sm text-muted-foreground">Cost: {renovationCost} coppers</p>
        )}
        <div className="flex max-h-96 flex-col gap-2 overflow-y-auto">
          {kinds.isLoading && <p className="text-sm text-muted-foreground">Loading catalog…</p>}
          {available.map((kind) => (
            <div key={kind.id} className="rounded-md border p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold">{kind.name}</span>
                <Button size="sm" onClick={() => renovate(kind.name)}>
                  Renovate
                </Button>
              </div>
              {kind.description && (
                <p className="mt-1 text-xs text-muted-foreground">{kind.description}</p>
              )}
              <div className="mt-1 flex flex-wrap gap-1">
                {KIND_FLAGS.filter((flag) => kind[flag.field]).map((flag) => (
                  <Badge key={flag.field} variant="outline">
                    {flag.label}
                  </Badge>
                ))}
              </div>
            </div>
          ))}
          {kinds.data && available.length === 0 && (
            <p className="text-sm text-muted-foreground">No other kinds available.</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
