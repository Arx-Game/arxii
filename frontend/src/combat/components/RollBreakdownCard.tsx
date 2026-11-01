/**
 * RollBreakdownCard: a recorded roll laid out as rows (#4858).
 *
 * A heading ("Hit roll against Bandit's defense", "Damage roll"), one row per source
 * (the strike skill and its rating, the stat, misses adding to hit, the weapon and its
 * quality) with why it counts, then the result line ("Hit, good", "11 damage").
 */

import type { components } from '@/generated/api';

export type RollBreakdown = components['schemas']['RollBreakdown'];

export function RollBreakdownCard({ breakdown }: { breakdown: RollBreakdown }) {
  return (
    <div className="space-y-1" data-testid="roll-breakdown">
      <p className="text-xs font-semibold text-foreground" data-testid="roll-heading">
        {breakdown.heading}
      </p>
      <div className="divide-y divide-border border-y border-border">
        {breakdown.lines.map((line) => (
          <div
            key={`${line.label}-${line.detail}`}
            className="flex items-baseline justify-between gap-3 py-1 text-xs"
            data-testid="roll-line"
          >
            <span className="text-foreground">
              {line.label}
              {line.value !== '' && (
                <span className="ml-1.5 font-mono text-muted-foreground">{line.value}</span>
              )}
            </span>
            <span className="text-right text-[11px] text-muted-foreground">{line.detail}</span>
          </div>
        ))}
        <div className="flex items-baseline justify-between gap-3 py-1 text-xs">
          <span className="font-semibold text-foreground" data-testid="roll-result">
            {breakdown.result}
          </span>
          {breakdown.result_note !== '' && (
            <span
              className="text-right text-[11px] text-muted-foreground"
              data-testid="roll-result-note"
            >
              {breakdown.result_note}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
