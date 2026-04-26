/**
 * BeatRow — single beat in the current episode beat list.
 *
 * Shows title/hint, outcome pill, aggregate progress bar, deadline, and
 * resolution text for completed beats.
 */

import { formatRelativeTime } from '@/lib/relativeTime';
import { BeatOutcomeBadge } from './BeatOutcomeBadge';
import { AggregateProgressBar } from './AggregateProgressBar';
import type { Beat } from '../types';

interface BeatRowProps {
  beat: Beat;
  /** Sum of contribution points for AGGREGATE_THRESHOLD beats (fetched by parent). */
  aggregateTotal?: number;
}

export function BeatRow({ beat, aggregateTotal = 0 }: BeatRowProps) {
  const isAggregate = beat.predicate_type === 'aggregate_threshold';
  const hasDeadline = beat.deadline != null;
  const outcome = beat.outcome ?? 'unsatisfied';
  const isResolved = outcome === 'success' || outcome === 'failure' || outcome === 'expired';

  // Visible title: player_hint if set, otherwise a generic label
  const visibleTitle =
    beat.player_hint && beat.player_hint.trim().length > 0
      ? beat.player_hint
      : beat.visibility === 'secret'
        ? '(Hidden Beat)'
        : 'Beat';

  return (
    <li className="space-y-2 rounded-md border bg-card p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="text-sm font-medium">{visibleTitle}</span>
        <BeatOutcomeBadge outcome={outcome} />
      </div>

      {isAggregate && beat.required_points != null && (
        <AggregateProgressBar current={aggregateTotal} required={beat.required_points} />
      )}

      {hasDeadline && !isResolved && (
        <p className="text-xs text-muted-foreground">
          Expires {formatRelativeTime(beat.deadline!)}
        </p>
      )}

      {outcome === 'success' && beat.player_resolution_text && (
        <p className="text-sm text-foreground/80">{beat.player_resolution_text}</p>
      )}
    </li>
  );
}
