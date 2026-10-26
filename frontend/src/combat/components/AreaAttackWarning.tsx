/**
 * AreaAttackWarning — a wound-up attack will cover the place she stands in (#4676,
 * demo Screen 4).
 *
 * Shown in Your Turn while a pending attack's covered place is the viewer's own place.
 * Only leaving the place escapes it: she walks out from the move list, or plans a dodge
 * that lands outside it ("Leap clear to ..."). "Brace" dodges in place, which does not
 * escape it.
 */

import type { components } from '@/generated/api';
import type { DispatchActionRequest, DispatchResult } from '@/combat/types';
import { attacksCoveringPlace, dodgeRequest } from '@/combat/dodging';

type PendingAttack = components['schemas']['PendingAttack'];
type DodgePlan = components['schemas']['DodgePlan'];

export interface AreaAttackWarningProps {
  attacks: PendingAttack[];
  currentPositionId: number | null;
  plan: DodgePlan | null;
  isLocked: boolean;
  dispatchAction: (params: DispatchActionRequest) => Promise<DispatchResult>;
  onDispatched?: () => void;
}

export function AreaAttackWarning({
  attacks,
  currentPositionId,
  plan,
  isLocked,
  dispatchAction,
  onDispatched,
}: AreaAttackWarningProps) {
  const covering = attacksCoveringPlace(attacks, currentPositionId);
  if (covering.length === 0) return null;
  const clear = (plan?.options ?? []).filter((option) => option.id !== currentPositionId);
  const send = (kwargs: Record<string, unknown>) => {
    dispatchAction(dodgeRequest(kwargs))
      .then(() => onDispatched?.())
      .catch(() => {});
  };

  return (
    <div className="space-y-2" data-testid="area-attack-warning">
      {covering.map((attack) => (
        <div
          key={attack.id}
          className="space-y-1.5 rounded-md border border-destructive/60 bg-destructive/10 p-3 text-sm"
        >
          <p>
            <b>{attack.attack_name}</b> will cover the whole {attack.covered_position_name} when it
            lands.
          </p>
          <p>
            Leaning aside won't help. Get out of the {attack.covered_position_name}, or take it.
          </p>
          {plan !== null && (
            <div className="flex flex-wrap gap-1.5">
              {clear.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  disabled={isLocked}
                  data-testid={`leap-clear-${option.id}`}
                  onClick={() => send({ position_id: option.id })}
                  className="rounded bg-primary px-2.5 py-1 text-xs font-semibold text-primary-foreground disabled:opacity-50"
                >
                  Leap clear to {option.name}
                </button>
              ))}
              <button
                type="button"
                disabled={isLocked}
                data-testid="area-brace"
                onClick={() => send({})}
                className="rounded bg-muted px-2.5 py-1 text-xs font-semibold disabled:opacity-50"
              >
                Brace
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
