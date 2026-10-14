/**
 * InvocationResult (#4333) — what a resolved option's Call on favor did, for the acting player.
 *
 * The two mission log lines (their own call line, then the outcome), and the check's breakdown
 * with the favor line: points before the bonus, the labelled bonus, the total and its rank
 * against the difficulty's rank. A bonus changes a result only when it moves the total across
 * a rank threshold, which is why the ranks are shown. The d100 roll is never shown.
 */
import type { components } from '@/generated/api';

type BeatInvocation = components['schemas']['BeatInvocation'];

export function InvocationResult({ invocation }: { invocation: BeatInvocation }) {
  return (
    <div className="space-y-1" data-testid="invocation-result-block">
      <div
        className="border-l-2 border-amber-600 pl-2 text-sm dark:border-amber-400"
        data-testid="invocation-call-line"
      >
        {invocation.call_line}
      </div>
      <div className="text-sm italic text-muted-foreground" data-testid="invocation-outcome-line">
        {invocation.outcome_line}
      </div>
      <dl
        className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-0.5 text-xs tabular-nums text-muted-foreground"
        data-testid="invocation-breakdown"
      >
        <dt>{invocation.check_type_name}</dt>
        <dd className="text-right">{invocation.points_before_bonus}</dd>
        {invocation.bonus ? (
          <>
            <dt className="font-semibold text-amber-700 dark:text-amber-400">
              {invocation.bonus_label}
            </dt>
            <dd className="text-right font-semibold text-amber-700 dark:text-amber-400">
              +{invocation.bonus}
            </dd>
          </>
        ) : (
          <>
            <dt>Invocation</dt>
            <dd className="text-right">no bonus</dd>
          </>
        )}
        <dt>Total</dt>
        <dd className="text-right">
          {invocation.total_points}
          {invocation.roller_rank ? `, rank ${invocation.roller_rank}` : ''}
        </dd>
        {invocation.target_rank ? (
          <>
            <dt>Difficulty</dt>
            <dd className="text-right">rank {invocation.target_rank}</dd>
            <dt>Rank difference</dt>
            <dd className="text-right">{invocation.rank_difference}</dd>
          </>
        ) : null}
      </dl>
    </div>
  );
}
