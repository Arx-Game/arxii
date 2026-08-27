/**
 * GMPlacementControls — shared GM-place "Place" toggle + target picker (#3385).
 *
 * `CombatTacticalMap` and `SceneTacticalMap` both need identical UI (a toggle
 * button + target `<select>`) and identical dispatch/invalidate logic for
 * gm_place_in_position, differing only in how they build the `gmPlaceActions`/
 * `targets` lists and how they invalidate their own query on success. This
 * component owns the shared state (`isPlacing`/`placeTargetId`), the shared
 * click handler, and the shared markup; callers render their `TacticalMap`
 * inside the render-prop `children`, which receives the `onGMPlace` handler
 * to forward as `TacticalMap`'s `onGMPlace` prop (`undefined` unless placing
 * is active and a target is selected).
 */

import { useState } from 'react';
import type { ReactNode } from 'react';
import { toast } from 'sonner';
import type { DispatchActionRequest, DispatchResult } from '@/combat/types';
import { isDispatchFailure } from '@/combat/types';
import type { PlayerAction } from '@/scenes/actionTypes';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

export interface GMPlacementTarget {
  id: number;
  name: string;
}

export interface GMPlacementControlsProps {
  /**
   * gm_place_in_position PlayerActions, one per Position — a non-empty list is
   * itself the "am I GM" signal (mirrors the `setTheStageAction` pattern):
   * the adapter only ever emits these when the caller already passes the
   * server-side GM gate.
   */
  gmPlaceActions: PlayerAction[];
  /** Co-located placeable targets: participants/opponents (combat) or personas (scene). */
  targets: GMPlacementTarget[];
  dispatchAction: (args: DispatchActionRequest) => Promise<DispatchResult>;
  /** Called after a successful placement — typically invalidates the encounter/scene query. */
  onPlaced: () => void;
  /** Render prop receiving the `onGMPlace` handler to hand to `TacticalMap`. */
  children: (onGMPlace: ((positionId: number) => boolean) | undefined) => ReactNode;
}

export function GMPlacementControls({
  gmPlaceActions,
  targets,
  dispatchAction,
  onPlaced,
  children,
}: GMPlacementControlsProps) {
  const [isPlacing, setIsPlacing] = useState(false);
  const [placeTargetId, setPlaceTargetId] = useState<number | null>(null);

  const handleGMPlace = (positionId: number): boolean => {
    if (placeTargetId == null) {
      return false;
    }
    const action = gmPlaceActions.find((a) => a.ref.position_id === positionId);
    if (!action) {
      return false;
    }
    dispatchAction({ ref: action.ref, kwargs: { target_object_id: placeTargetId } })
      .then((result) => {
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'Placement rejected.');
          return;
        }
        setPlaceTargetId(null);
        onPlaced();
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Placement failed.');
      });
    return true;
  };

  const onGMPlace = isPlacing && placeTargetId != null ? handleGMPlace : undefined;

  return (
    <>
      {gmPlaceActions.length > 0 && (
        <div className="flex items-center gap-2" data-testid="gm-place-controls">
          <Button
            type="button"
            variant={isPlacing ? 'default' : 'outline'}
            size="sm"
            data-testid="gm-place-toggle"
            onClick={() => {
              setIsPlacing((prev) => !prev);
              setPlaceTargetId(null);
            }}
          >
            Place
          </Button>
          {isPlacing && (
            <Select
              value={placeTargetId !== null ? String(placeTargetId) : ''}
              onValueChange={(v) => setPlaceTargetId(v === '' ? null : Number(v))}
            >
              <SelectTrigger className="h-8 w-48 text-xs" data-testid="gm-place-target-select">
                <SelectValue placeholder="Select a target…" />
              </SelectTrigger>
              <SelectContent>
                {targets.map((target) => (
                  <SelectItem key={target.id} value={String(target.id)}>
                    {target.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      )}
      {children(onGMPlace)}
    </>
  );
}
