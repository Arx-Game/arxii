/**
 * DodgePlanPanel — "If you're attacked this round" (#4676, demo Screen 3).
 *
 * The dodge itself is automatic on the server; this sets whether to dodge and where to
 * land, through the `combat_dodge` registry action. Shown only when the viewer's own
 * participant row carries a `dodge_plan` (the server sends it to its owner only, and
 * only when something she has lets her dodge).
 */

import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import type { components } from '@/generated/api';
import { isDispatchFailure, type DispatchActionRequest, type DispatchResult } from '@/combat/types';
import { dodgeRequest } from '@/combat/dodging';

type DodgePlan = components['schemas']['DodgePlan'];

export interface DodgePlanPanelProps {
  plan: DodgePlan;
  /** The viewer's own place now: the first option is always where she stands. */
  currentPositionId: number | null;
  isLocked: boolean;
  dispatchAction: (params: DispatchActionRequest) => Promise<DispatchResult>;
  onDispatched?: () => void;
}

export function DodgePlanPanel({
  plan,
  currentPositionId,
  isLocked,
  dispatchAction,
  onDispatched,
}: DodgePlanPanelProps) {
  const send = (kwargs: Record<string, unknown>) => {
    dispatchAction(dodgeRequest(kwargs))
      .then((result) => {
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'That plan was refused.');
          return;
        }
        onDispatched?.();
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'That plan was refused.');
      });
  };

  const elsewhere = plan.options.filter((option) => option.id !== currentPositionId);
  const inPlace = plan.enabled && plan.landing_id === null;

  return (
    <section className="space-y-1.5" data-testid="dodge-plan">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        If you're attacked this round
      </h3>
      <DodgeOption
        label="Dodge in place"
        chosen={inPlace}
        disabled={isLocked}
        testId="dodge-in-place"
        onClick={() => send({})}
      />
      {elsewhere.map((option) => (
        <DodgeOption
          key={option.id}
          label={`Dodge to ${option.name}`}
          chosen={plan.enabled && plan.landing_id === option.id}
          disabled={isLocked}
          testId={`dodge-to-${option.id}`}
          onClick={() => send({ position_id: option.id })}
        />
      ))}
      <DodgeOption
        label="Don't dodge"
        chosen={!plan.enabled}
        disabled={isLocked}
        testId="dodge-off"
        onClick={() => send({ dodge: false })}
      />
      <p className="text-xs text-muted-foreground" data-testid="dodge-cost">
        {plan.cost_line}
      </p>
    </section>
  );
}

function DodgeOption({
  label,
  chosen,
  disabled,
  testId,
  onClick,
}: {
  label: string;
  chosen: boolean;
  disabled: boolean;
  testId: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      aria-pressed={chosen}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'w-full rounded border px-3 py-1.5 text-left text-sm',
        chosen ? 'border-primary bg-primary/10 font-medium' : 'border-border hover:bg-muted/50',
        disabled && 'cursor-not-allowed opacity-50'
      )}
    >
      {label}
    </button>
  );
}
