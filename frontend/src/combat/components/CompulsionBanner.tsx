/**
 * CompulsionBanner and CompulsionMark (#4802, demo Screen 2).
 *
 * The server sends `compulsion` to the character's own player only. The banner says what
 * the compulsion wants; the mark outlines each declarable action that goes against it and
 * shows the difficulty of the resist check it needs.
 */

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import type { components } from '@/generated/api';

export type Compulsion = components['schemas']['Compulsion'];
export type ActionCost = Compulsion['against'][number];

/** The panel key for a technique that names no opponent (a defend, a heal). */
export const NO_TARGET_TECHNIQUE_KEY = 'technique_no_target';

/** What declaring this action costs under the compulsion; null when it costs nothing. */
export function compulsionCost(
  compulsion: Compulsion | null | undefined,
  actionKey: string
): ActionCost | null {
  if (!compulsion) return null;
  return compulsion.against.find((cost) => cost.action_key === actionKey) ?? null;
}

/** "Forbidden, difficulty 36" or "Difficulty 31": the cost on a marked action. */
export function costLabel(cost: ActionCost): string {
  return `${cost.forbidden ? 'Forbidden, difficulty' : 'Difficulty'} ${cost.difficulty}`;
}

function lowerFirst(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}

export function CompulsionBanner({ compulsion }: { compulsion: Compulsion }) {
  return (
    <div
      role="status"
      data-testid="compulsion-banner"
      className="space-y-0.5 rounded-md border border-red-500/60 bg-red-50 px-3 py-2 text-sm dark:bg-red-950/40"
    >
      <p className="font-semibold text-red-800 dark:text-red-300">
        {compulsion.condition_name} compels: {lowerFirst(compulsion.wants_label)}.
      </p>
      <p className="text-red-900 dark:text-red-200">
        Attacking is free. Any other action needs a {compulsion.check_name} check this round. If the
        check fails, you attack instead.
      </p>
    </div>
  );
}

export function CompulsionMark({
  compulsion,
  actionKey,
  children,
}: {
  compulsion: Compulsion | null | undefined;
  actionKey: string;
  children: ReactNode;
}) {
  const cost = compulsionCost(compulsion, actionKey);
  if (cost === null) return <>{children}</>;
  return (
    <div
      data-testid={`compulsion-mark-${actionKey}`}
      className={cn(
        'space-y-1 rounded-md ring-2 ring-red-500/70 ring-offset-1 ring-offset-background'
      )}
    >
      {children}
      <p
        className="px-2 pb-1 text-xs font-medium text-red-700 dark:text-red-300"
        data-testid={`compulsion-difficulty-${actionKey}`}
      >
        {costLabel(cost)}
      </p>
    </div>
  );
}

/** The ring and the cost for a menu item, which cannot hold a wrapping block. */
export const COMPULSION_ITEM_CLASS = 'ring-1 ring-red-500/70';

export function CompulsionCostTag({ cost }: { cost: ActionCost }) {
  return (
    <span
      className="ml-auto pl-3 text-xs font-medium text-red-700 dark:text-red-300"
      data-testid="compulsion-cost-tag"
    >
      {costLabel(cost)}
    </span>
  );
}

/** The line under the chosen action: what the check is and what makes it hard. */
export function CompulsionChosenLine({
  compulsion,
  actionKey,
}: {
  compulsion: Compulsion;
  actionKey: string;
}) {
  const cost = compulsionCost(compulsion, actionKey);
  if (cost === null) return null;
  const { condition_name: name, check_name: check } = compulsion;
  return (
    <p
      className="rounded-md border border-red-500/60 bg-red-50 px-3 py-2 text-sm text-red-900 dark:bg-red-950/40 dark:text-red-200"
      data-testid="compulsion-chosen-line"
    >
      <span className="font-semibold">Against {name}.</span>{' '}
      {cost.forbidden
        ? `${name} forbids ${cost.label}: ${check} check, difficulty ${cost.difficulty} ` +
          `(${cost.difficulty - cost.extra_difficulty} to resist, +${cost.extra_difficulty} ` +
          'because it is forbidden).'
        : `${check} check, difficulty ${cost.difficulty}.`}{' '}
      {compulsion.attack_target_name
        ? `If the check fails, you strike ${compulsion.attack_target_name} with your simplest attack, as things stand.`
        : 'If the check fails, you do not act, as things stand.'}
    </p>
  );
}
