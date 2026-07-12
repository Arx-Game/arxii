/**
 * EncounterOutcomeBanner — terminal-state banner for a completed encounter.
 *
 * Rendered by CombatTurnPanel in place of the live rail sections once the
 * encounter status is "completed" (#876). The Narrator OUTCOME line in the
 * pose log carries the prose; this banner is the at-a-glance verdict.
 *
 * Previously carried a "Return to Scene" link (#2157) back to the scene the
 * encounter belonged to — combat lived on its own /scenes/:id/combat route,
 * so without it a player was stranded there. #2197 folded CombatRail (and
 * this banner) into the scene page itself, so that link would now point at
 * the very page it renders on; removed as dead/self-referential.
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
    <div className="flex flex-col items-center gap-3">
      <div
        role="status"
        className={cn(
          'w-full rounded-md border px-4 py-3 text-center text-lg font-semibold tracking-wide',
          style.className
        )}
      >
        {style.label}
      </div>
    </div>
  );
}
