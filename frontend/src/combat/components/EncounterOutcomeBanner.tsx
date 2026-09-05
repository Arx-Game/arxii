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
import { AftermathDigest } from './AftermathDigest';

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

export interface EncounterOutcomeDigestEntry {
  participantId: number;
  characterName: string;
  digest: AftermathDigest;
}

export interface EncounterOutcomeBannerProps {
  outcome: string;
  /** One aftermath digest per participant the viewer is allowed to see (#3551). */
  digests?: EncounterOutcomeDigestEntry[];
  /** Shown as a Dismiss button when provided, clearing the lingering rail (#3551). */
  onDismiss?: () => void;
}

export function EncounterOutcomeBanner({
  outcome,
  digests,
  onDismiss,
}: EncounterOutcomeBannerProps) {
  const style = OUTCOME_STYLES[outcome] ?? OUTCOME_STYLES.abandoned;
  const showTitles = (digests?.length ?? 0) > 1;
  return (
    <div className="flex flex-col items-center gap-3">
      <output
        className={cn(
          'block',
          'w-full rounded-md border px-4 py-3 text-center text-lg font-semibold tracking-wide',
          style.className
        )}
      >
        {style.label}
      </output>

      {digests && digests.length > 0 && (
        <div className="w-full space-y-3">
          {digests.map((entry) => (
            <AftermathDigest
              key={entry.participantId}
              digest={entry.digest}
              title={showTitles ? entry.characterName : undefined}
            />
          ))}
        </div>
      )}

      {onDismiss && (
        <button
          type="button"
          data-testid="aftermath-dismiss"
          onClick={onDismiss}
          className="rounded-md border border-border px-3 py-1.5 text-xs font-semibold text-muted-foreground hover:bg-muted"
        >
          Dismiss
        </button>
      )}
    </div>
  );
}
