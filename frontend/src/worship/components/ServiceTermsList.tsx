/**
 * ServiceTermsList (#4333) — the system-generated list of what earns favor with a being for
 * one character: each kind of deed with its share, sacrifices, the being's other acts, and the
 * character's earning rate in its parts. Used by the Pledge yourself dialog and the pledge card.
 */

import { earningRateParts } from '../pledgeText';
import type { ServiceTerms } from '../types';

export function ServiceTermsList({ terms }: { terms: ServiceTerms }) {
  return (
    <div className="space-y-1" data-testid="service-terms">
      <ul className="divide-y divide-dotted text-sm">
        {terms.lines.map((line) => (
          <li key={line.label} className="flex justify-between gap-3 py-1">
            <span>{line.label}</span>
            <span className="shrink-0 font-semibold tabular-nums text-amber-700 dark:text-amber-400">
              {line.amount}
            </span>
          </li>
        ))}
        <li className="flex justify-between gap-3 py-1" data-testid="earning-rate">
          <span>
            <b>Your earning rate: {terms.rate.total}%</b>{' '}
            <span className="text-muted-foreground">({earningRateParts(terms)})</span>
          </span>
          <span className="shrink-0 font-semibold text-amber-700 dark:text-amber-400">
            applies to all
          </span>
        </li>
      </ul>
      <p className="text-xs text-muted-foreground">
        <b>Rule:</b> base favor from deeds is capped at {terms.weekly_deed_cap} a week, counted
        before your earning rate.
      </p>
    </div>
  );
}
