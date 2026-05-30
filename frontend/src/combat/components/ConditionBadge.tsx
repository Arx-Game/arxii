/**
 * ConditionBadge — small chip representing a single active condition on a
 * combatant. Renders the condition's icon, tinted by its `color_hex`, and
 * deep-links to the shared condition-detail modal on click.
 *
 * Reuses the existing deep-link slice (`openDeepLink`) + `ConditionDetailModal`
 * (mounted via DeepLinkModalHost) — no new modal or dispatch path. (#553)
 */

import { useAppDispatch } from '@/store/hooks';
import { openDeepLink } from '@/store/deepLinkModalSlice';
import type { components } from '@/generated/api';

type ConditionInstance = components['schemas']['ConditionInstance'];

export interface ConditionBadgeProps {
  condition: ConditionInstance;
}

/** Build the tooltip text: name plus stage/stacks when present. */
function buildTooltip(condition: ConditionInstance): string {
  const parts: string[] = [condition.name];
  if (condition.stage_name) {
    parts.push(`(${condition.stage_name})`);
  }
  if (typeof condition.stacks === 'number' && condition.stacks > 1) {
    parts.push(`x${condition.stacks}`);
  }
  return parts.join(' ');
}

export function ConditionBadge({ condition }: ConditionBadgeProps) {
  const dispatch = useAppDispatch();
  const tooltip = buildTooltip(condition);

  return (
    <button
      type="button"
      title={tooltip}
      aria-label={tooltip}
      onClick={() => dispatch(openDeepLink({ modal: 'condition', id: condition.id }))}
      className="inline-flex h-5 min-w-5 items-center justify-center rounded-full border px-1 text-xs leading-none hover:opacity-80 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      style={{ borderColor: condition.color_hex, color: condition.color_hex }}
      data-testid={`condition-badge-${condition.id}`}
    >
      <span aria-hidden="true">{condition.icon}</span>
    </button>
  );
}
