/**
 * PromoteAreaButton — the selected area's origin badge plus a "Promote to
 * authored" affordance for the `WorldBuilderPage` header (#2449 fix pass).
 * Mirrors `RoomDetailPanel`'s inline `promote_room` AlertDialog pattern
 * (`./RoomDetailPanel.tsx`) — stamps a permanent slug and marks the area
 * AUTHORED for export. `slug` is left unset so `PromoteAreaAction`
 * (`src/actions/definitions/world_builder.py`) suggests one from the area's
 * name, same as `promote_room` leaving `fixture_key` unset.
 */
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

import type { WorldBuilderActionKey, WorldBuilderArea } from '../types';

export interface PromoteAreaButtonProps {
  area: WorldBuilderArea;
  runAction: (key: WorldBuilderActionKey, kwargs: Record<string, unknown>) => void;
}

export function PromoteAreaButton({ area, runAction }: PromoteAreaButtonProps) {
  return (
    <>
      <Badge variant={area.origin === 'authored' ? 'default' : 'secondary'}>{area.origin}</Badge>
      {area.origin !== 'authored' && (
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button type="button" size="sm" variant="outline">
              Promote area
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Promote {area.name}?</AlertDialogTitle>
              <AlertDialogDescription>
                Stamps a permanent slug and marks the area AUTHORED for export. This cannot be
                undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => runAction('promote_area', { area_id: area.id })}>
                Promote
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </>
  );
}
