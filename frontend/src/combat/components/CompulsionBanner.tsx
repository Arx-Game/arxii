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
type ActionCost = Compulsion['against'][number];

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
        {cost.forbidden ? 'Forbidden, difficulty' : 'Difficulty'} {cost.difficulty}
      </p>
    </div>
  );
}
