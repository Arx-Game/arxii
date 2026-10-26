/**
 * MovementActions — reusable move-to-position button list.
 *
 * Extracted from YourTurn.tsx (lines 655–685) to share with the
 * non-combat SceneTacticalMap.  Renders one button per move action (a step,
 * a take-off or landing, a pass roll into held ground, #4663, a stunt off a feature,
 * #4675) with the server's note under it; clicking dispatches `{ ref, kwargs: {} }` via the
 * caller-supplied dispatchAction function and toasts the result's message.
 */

import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import type { PlayerAction } from '@/scenes/actionTypes';
import { hopsLeftLine } from '@/combat/roundActionHelpers';
import { isDispatchFailure, type DispatchActionRequest, type DispatchResult } from '@/combat/types';

export interface MovementActionsProps {
  actions: PlayerAction[];
  isLocked: boolean;
  dispatchAction: (params: DispatchActionRequest) => Promise<DispatchResult>;
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

  // While the round is open the server puts "N hops left this round." on each move it offers.
  const hopsLine = hopsLeftLine(actions);

  return (
    <div className="space-y-2" data-testid="movement-section">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Move</p>
      {hopsLine !== null && (
        <p className="text-xs text-muted-foreground" data-testid="movement-hops-line">
          {hopsLine}
        </p>
      )}
      {actions.map((action) => {
        const positionId = action.ref.position_id;
        const refused = !action.prerequisite_met;
        // A move and a pass roll can name the same place (#4663), and two stunts can reach
        // one place by different features or approaches (#4675): the key carries them all.
        const via = [action.ref.feature_id, action.ref.approach_id]
          .filter((id) => id != null)
          .map((id) => `-${id}`)
          .join('');
        const key = `${action.ref.registry_key ?? 'move'}-${positionId ?? 'here'}${via}`;
        // The hops line already shows above; any other note is this entry's own.
        const note =
          action.description && action.description !== hopsLine ? action.description : '';
        return (
          <button
            key={key}
            type="button"
            disabled={isLocked || refused}
            data-testid={`move-btn-${key}`}
            onClick={() => {
              dispatchAction({ ref: action.ref, kwargs: {} })
                .then((result) => {
                  if (isDispatchFailure(result)) {
                    toast.error(result.message ?? 'Move rejected.');
                    return;
                  }
                  if (result.message) toast.success(result.message);
                  onDispatched?.();
                })
                .catch((err: unknown) => {
                  toast.error(err instanceof Error ? err.message : 'Move failed.');
                });
            }}
            className={cn(
              'w-full rounded border px-3 py-1.5 text-left text-xs font-medium transition-colors',
              'disabled:cursor-not-allowed disabled:opacity-50',
              isLocked || refused
                ? 'border-border bg-muted text-muted-foreground'
                : 'border-amber-500/40 bg-amber-500/5 text-amber-300 hover:bg-amber-500/10'
            )}
          >
            {action.display_name}
            {note && !refused && (
              <span className="block text-[11px] font-normal" data-testid={`move-note-${key}`}>
                {note}
              </span>
            )}
            {refused && action.prerequisite_reasons[0] && (
              <span className="block text-[11px] font-normal">
                {action.prerequisite_reasons[0]}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
