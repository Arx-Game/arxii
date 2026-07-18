/**
 * CrimeTab (#1765) — where your active persona is wanted, and for what.
 *
 * Self-only risk information: only rendered on the player's own sheet, and the backend
 * scopes to the viewer's active persona. Each row is one warrant — an area, the society
 * hunting you there, the pursuit tier (color-coded ladder, never a raw number), and the
 * alleged deeds behind it. Allegations render as recorded: a false accusation reads the
 * same as a true one.
 */

import { Loader2 } from 'lucide-react';

import {
  useBribeMutation,
  useInitiateTrialMutation,
  useLieLowMutation,
  useMyCase,
  usePersonaHeat,
} from '../queries';
import type { PersonaHeatRow } from '../api';
import { Button } from '@/components/ui/button';

interface Props {
  /** The viewer's active RosterEntry pk; null when no character is active. */
  viewerEntryId: number | null;
}

const TIER_STYLES: Record<string, string> = {
  tense: 'bg-yellow-500/15 text-yellow-600 dark:text-yellow-400',
  dangerous: 'bg-orange-500/15 text-orange-600 dark:text-orange-400',
  heat_is_on: 'bg-red-500/15 text-red-600 dark:text-red-400',
  extreme_heat: 'bg-red-600/25 text-red-700 dark:text-red-300',
};

function TierBadge({ row }: { row: PersonaHeatRow }) {
  const style = TIER_STYLES[row.tier] ?? 'bg-muted text-muted-foreground';
  return (
    <span
      className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${style}`}
      data-testid="heat-tier-badge"
    >
      {row.tier_label}
    </span>
  );
}

/**
 * MyCaseCard (#2378) — the captive's own case: evidence progress toward release
 * and the one lever nobody else holds, calling their own trial.
 */
function MyCaseCard({ viewerEntryId }: { viewerEntryId: number }) {
  const { data: myCase } = useMyCase(viewerEntryId);
  const trial = useInitiateTrialMutation(viewerEntryId);

  if (!myCase) return null;

  return (
    <div className="rounded-lg border border-destructive/40 bg-card p-4" data-testid="my-case-card">
      <div className="flex items-baseline justify-between gap-3">
        <h4 className="font-medium">
          Held for trial in {myCase.area_name}
          <span className="ml-2 text-sm font-normal text-muted-foreground">
            {myCase.society_name}
          </span>
        </h4>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        Evidence in your favor: {myCase.evidence_total} of {myCase.release_threshold} needed for
        release without trial.
        {myCase.failed_outs > 0 && ` Failed escapes counted against you: ${myCase.failed_outs}.`}
      </p>
      {trial.data ? (
        <p className="mt-2 text-sm font-medium" data-testid="trial-verdict">
          Verdict: {trial.data.verdict}
          {trial.data.sentence_kind &&
            ` — ${trial.data.sentence_kind}${trial.data.sentence_amount ? ` (${trial.data.sentence_amount})` : ''}`}
        </p>
      ) : (
        <div className="mt-2">
          <Button
            size="sm"
            variant="outline"
            disabled={trial.isPending}
            onClick={() => trial.mutate({ caseId: myCase.id })}
            title="Call your moment before the magistrates. Friends' evidence and advocacy weigh in your favor; nobody argues against you but the record."
          >
            Stand trial now
          </Button>
        </div>
      )}
      {trial.isError && trial.error instanceof Error && (
        <p className="mt-1 text-sm text-destructive">{trial.error.message}</p>
      )}
    </div>
  );
}

export function CrimeTab({ viewerEntryId }: Props) {
  const { data: rows, isLoading } = usePersonaHeat(viewerEntryId);
  const lieLow = useLieLowMutation(viewerEntryId);
  const bribe = useBribeMutation(viewerEntryId);

  if (viewerEntryId === null) {
    return (
      <p className="py-8 text-center text-muted-foreground">
        No active character to view crime records for.
      </p>
    );
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!rows || rows.length === 0) {
    return (
      <div className="space-y-3">
        <MyCaseCard viewerEntryId={viewerEntryId} />
        <p className="py-8 text-center text-muted-foreground" data-testid="crime-empty-state">
          So far as you know, no one is hunting you anywhere.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <MyCaseCard viewerEntryId={viewerEntryId} />
      <ul className="space-y-3" data-testid="crime-list">
        {rows.map((row) => (
          <li key={row.id} className="rounded-lg border bg-card p-4" data-testid="crime-row">
            <div className="flex items-baseline justify-between gap-3">
              <h4 className="font-medium">
                {row.area_name}
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  {row.society_name}
                </span>
              </h4>
              <TierBadge row={row} />
            </div>
            {row.alleged_deeds.length > 0 && (
              <p className="mt-1 text-sm text-muted-foreground">
                Wanted for: {row.alleged_deeds.join(', ')}
              </p>
            )}
            <div className="mt-2 flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={lieLow.isPending}
                onClick={() => lieLow.mutate({ areaId: row.area })}
                title="Go to ground here: heat cools faster, but your rackets miss you. Any IC action here surfaces you."
              >
                Lie low
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={bribe.isPending}
                onClick={() => bribe.mutate({ areaId: row.area })}
                title="Approach the hunters with coin. Expensive; a botched approach is itself a crime."
              >
                Bribe the hunters
              </Button>
            </div>
            {(lieLow.isError || bribe.isError) && (
              <p className="mt-1 text-sm text-destructive">
                {[lieLow.error, bribe.error]
                  .filter((e): e is Error => e instanceof Error)
                  .map((e) => e.message)
                  .join(' ')}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
