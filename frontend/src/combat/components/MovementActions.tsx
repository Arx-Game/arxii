/**
 * MovementActions — reusable move-to-position button list.
 *
 * Extracted from YourTurn.tsx (lines 655–685) to share with the
 * non-combat SceneTacticalMap.  Renders one button per move action;
 * clicking dispatches `{ ref, kwargs: {} }` via the caller-supplied
 * dispatchAction function.
 */

import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import type { PlayerAction } from '@/scenes/actionTypes';
import { isDispatchFailure, type DispatchActionRequest, type DispatchResult } from '@/combat/types';

export interface MovementActionsProps {
  actions: PlayerAction[];
  isLocked: boolean;
  dispatchAction: (params: DispatchActionRequest) => Promise<unknown>;
  /** Fires after a successful move dispatch — callers invalidate the encounter so the
   *  move shows before the next poll. */
  onDispatched?: () => void;
}

export function MovementActions({
  actions,
  isLocked,
  dispatchAction,
  onDispatched,
}: MovementActionsProps) {
  if (actions.length === 0) return null;

  return (
    <div className="space-y-2" data-testid="movement-section">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Move</p>
      {actions.map((action) => {
        const positionId = action.ref.position_id;
        return (
          <button
            key={positionId ?? action.display_name}
            type="button"
            disabled={isLocked}
            data-testid={`move-btn-${positionId ?? 'unknown'}`}
            onClick={() => {
              dispatchAction({ ref: action.ref, kwargs: {} })
                .then((result) => {
                  if (isDispatchFailure(result as DispatchResult)) {
                    toast.error((result as DispatchResult).message ?? 'Move rejected.');
                    return;
                  }
                  onDispatched?.();
                })
                .catch((err: unknown) => {
                  toast.error(err instanceof Error ? err.message : 'Move failed.');
                });
            }}
            className={cn(
              'w-full rounded border px-3 py-1.5 text-left text-xs font-medium transition-colors',
              'disabled:cursor-not-allowed disabled:opacity-50',
              isLocked
                ? 'border-border bg-muted text-muted-foreground'
                : 'border-amber-500/40 bg-amber-500/5 text-amber-300 hover:bg-amber-500/10'
            )}
          >
            {action.display_name}
          </button>
        );
      })}
    </div>
  );
}
