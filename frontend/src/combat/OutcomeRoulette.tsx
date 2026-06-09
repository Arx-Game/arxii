/**
 * OutcomeRoulette — consequence outcome display component.
 *
 * Shows the full weighted pool of possible outcomes (the roulette) for a
 * resolved consequence, highlighting the tier that actually fired, plus a
 * breakdown of what modified the roll (modifier provenance).
 *
 * Phase 5 of the consequence-outcome display plan (#850).
 */

import { cn } from '@/lib/utils';
import type { ConsequenceOutcomeModifier, OutcomeDisplayRow } from './api';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface OutcomeRouletteProps {
  /** The full weighted outcome pool, with is_selected marking the winner. */
  outcomeDisplay: OutcomeDisplayRow[];
  /** The modifier breakdown — each entry is a source that shifted the roll. */
  modifiers: ConsequenceOutcomeModifier[];
  /** Net modifier total (sum of all modifier values). */
  modifierTotal: number;
  /** Optional summary string from the backend. */
  summary?: string;
}

// ---------------------------------------------------------------------------
// Tier color map — visual hierarchy for outcome severity
// ---------------------------------------------------------------------------

const TIER_COLOR: Record<string, string> = {
  // Common tier names from the consequence pool (case-insensitive keys not used —
  // the tier_name comes from authored content; we normalise to lowercase for lookup).
  trivial: 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300',
  minor: 'bg-sky-500/20 border-sky-500/40 text-sky-300',
  moderate: 'bg-amber-500/20 border-amber-500/40 text-amber-300',
  serious: 'bg-orange-500/20 border-orange-500/40 text-orange-300',
  severe: 'bg-rose-500/20 border-rose-500/40 text-rose-300',
  catastrophic: 'bg-violet-600/20 border-violet-600/40 text-violet-300',
};

function tierColorClass(tierName: string): string {
  return TIER_COLOR[tierName.toLowerCase()] ?? 'bg-muted border-border text-muted-foreground';
}

// ---------------------------------------------------------------------------
// WeightBar — one outcome row with proportional bar and selected highlight
// ---------------------------------------------------------------------------

interface WeightBarProps {
  row: OutcomeDisplayRow;
  totalWeight: number;
}

function WeightBar({ row, totalWeight }: WeightBarProps) {
  const pct = totalWeight > 0 ? Math.round((row.weight / totalWeight) * 100) : 0;
  const colorClass = tierColorClass(row.tier_name);

  return (
    <div
      className={cn(
        'relative flex items-center gap-2 rounded border px-2 py-1.5 transition-all',
        row.is_selected
          ? cn(colorClass, 'ring-1 ring-current ring-offset-1 ring-offset-background')
          : 'border-border bg-muted/20 text-muted-foreground'
      )}
      data-testid={`outcome-row-${row.tier_name}`}
      aria-selected={row.is_selected}
    >
      {/* Weight percentage bar in the background */}
      <div
        className={cn(
          'absolute inset-y-0 left-0 rounded opacity-20',
          row.is_selected ? 'bg-current' : 'bg-muted-foreground/30'
        )}
        style={{ width: `${pct}%` }}
        aria-hidden="true"
      />

      {/* Foreground content */}
      <span className="relative shrink-0 font-mono text-[10px]">{pct}%</span>
      <span className="relative min-w-0 flex-1 truncate text-xs font-medium">{row.label}</span>
      <span
        className={cn(
          'relative shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold',
          row.is_selected ? colorClass : 'bg-muted text-muted-foreground'
        )}
        data-testid={`outcome-tier-${row.tier_name}`}
      >
        {row.tier_name}
      </span>
      {row.is_selected && (
        <span
          className="relative shrink-0 text-[10px] font-bold"
          data-testid={`outcome-selected-marker-${row.tier_name}`}
          aria-label="This outcome was selected"
        >
          ✓
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ModifierRow — one modifier contribution line
// ---------------------------------------------------------------------------

interface ModifierRowProps {
  modifier: ConsequenceOutcomeModifier;
}

function ModifierRow({ modifier }: ModifierRowProps) {
  const signed = modifier.value >= 0 ? `+${modifier.value}` : String(modifier.value);
  const isPositive = modifier.value > 0;
  const isNegative = modifier.value < 0;

  return (
    <div
      className="flex items-center justify-between text-xs"
      data-testid={`modifier-row-${modifier.source_label}`}
    >
      <span className="truncate text-muted-foreground">{modifier.source_label}</span>
      <span
        className={cn(
          'ml-2 shrink-0 font-mono font-semibold',
          isPositive && 'text-emerald-400',
          isNegative && 'text-rose-400',
          !isPositive && !isNegative && 'text-muted-foreground'
        )}
        data-testid={`modifier-value-${modifier.source_label}`}
      >
        {signed}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// OutcomeRoulette
// ---------------------------------------------------------------------------

export function OutcomeRoulette({
  outcomeDisplay,
  modifiers,
  modifierTotal,
  summary,
}: OutcomeRouletteProps) {
  const totalWeight = outcomeDisplay.reduce((sum, r) => sum + r.weight, 0);
  const selectedRow = outcomeDisplay.find((r) => r.is_selected);

  const signedTotal = modifierTotal >= 0 ? `+${modifierTotal}` : String(modifierTotal);

  return (
    <div className="space-y-3" data-testid="outcome-roulette">
      {/* Summary line */}
      {summary && (
        <p className="text-xs text-muted-foreground" data-testid="outcome-summary">
          {summary}
        </p>
      )}

      {/* Selected result callout */}
      {selectedRow && (
        <div
          className={cn(
            'flex items-center gap-2 rounded border px-3 py-2',
            tierColorClass(selectedRow.tier_name)
          )}
          data-testid="outcome-selected-callout"
        >
          <span className="text-sm font-bold">Result:</span>
          <span className="flex-1 truncate text-sm">{selectedRow.label}</span>
          <span className="shrink-0 text-xs font-semibold">{selectedRow.tier_name}</span>
        </div>
      )}

      {/* Roulette pool — all possible outcomes */}
      {outcomeDisplay.length > 0 && (
        <div className="space-y-1" data-testid="outcome-pool">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Outcome Pool
          </p>
          {outcomeDisplay.map((row) => (
            <WeightBar key={`${row.tier_name}-${row.label}`} row={row} totalWeight={totalWeight} />
          ))}
        </div>
      )}

      {/* Modifier breakdown — only shown when there are modifiers */}
      {modifiers.length > 0 && (
        <div className="space-y-1" data-testid="modifier-breakdown">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Modifiers
          </p>
          <div className="space-y-0.5 rounded border border-border bg-muted/20 px-2 py-2">
            {modifiers.map((m) => (
              <ModifierRow key={`${m.source_kind}-${m.source_label}`} modifier={m} />
            ))}
            <div className="mt-1 flex items-center justify-between border-t border-border pt-1 text-xs font-semibold">
              <span className="text-muted-foreground">Total modifier</span>
              <span
                className={cn(
                  'font-mono',
                  modifierTotal > 0 && 'text-emerald-400',
                  modifierTotal < 0 && 'text-rose-400',
                  modifierTotal === 0 && 'text-muted-foreground'
                )}
                data-testid="modifier-total"
              >
                {signedTotal}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
