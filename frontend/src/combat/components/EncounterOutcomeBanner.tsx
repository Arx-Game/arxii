/**
 * EncounterOutcomeBanner — terminal-state banner for a completed encounter.
 *
 * Rendered by CombatTurnPanel in place of the live rail sections once the
 * encounter status is "completed" (#876). The Narrator OUTCOME line in the
 * pose log carries the prose; this banner is the at-a-glance verdict.
 */

import { cn } from '@/lib/utils';

const OUTCOME_STYLES: Record<string, { label: string; className: string }> = {
  victory: {
    label: 'Victory',
    className: 'border-emerald-500/60 bg-emerald-950/40 text-emerald-200',
  },
  defeat: { label: 'Defeat', className: 'border-red-600/60 bg-red-950/40 text-red-200' },
  fled: { label: 'Fled', className: 'border-amber-500/60 bg-amber-950/40 text-amber-200' },
  abandoned: {
    label: 'Abandoned',
    className: 'border-zinc-500/60 bg-zinc-900/40 text-zinc-300',
  },
};

export interface EncounterOutcomeBannerProps {
  outcome: string;
}

export function EncounterOutcomeBanner({ outcome }: EncounterOutcomeBannerProps) {
  const style = OUTCOME_STYLES[outcome] ?? OUTCOME_STYLES.abandoned;
  return (
    <div
      role="status"
      className={cn(
        'rounded-md border px-4 py-3 text-center text-lg font-semibold tracking-wide',
        style.className
      )}
    >
      {style.label}
    </div>
  );
}
