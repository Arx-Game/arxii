/**
 * BeatRow — single beat in the current episode beat list.
 *
 * Shows title/hint, outcome pill, aggregate progress bar, deadline, and
 * resolution text for completed beats.  For AGGREGATE_THRESHOLD beats
 * with a known characterSheetId, also renders the "Contribute" action.
 * For GM_MARKED beats renders the "Mark" action only when beat.can_mark
 * is true (server signals the requesting user has permission).
 */

import { formatRelativeTime } from '@/lib/relativeTime';
import { BeatOutcomeBadge } from './BeatOutcomeBadge';
import { AggregateProgressBar } from './AggregateProgressBar';
import { ContributeBeatDialog } from './ContributeBeatDialog';
import { MarkBeatDialog } from './MarkBeatDialog';
import type { Beat } from '../types';

interface BeatRowProps {
  beat: Beat;
  /** Sum of contribution points for AGGREGATE_THRESHOLD beats (fetched by parent). */
  aggregateTotal?: number;
  /**
   * Character sheet ID to pre-fill in the contribution dialog.
   * When provided, the "Contribute" button is rendered on aggregate beats.
   * For CHARACTER-scope stories this is story.character_sheet.
   */
  characterSheetId?: number | null;
}

export function BeatRow({ beat, aggregateTotal = 0, characterSheetId }: BeatRowProps) {
  const isAggregate = beat.predicate_type === 'aggregate_threshold';
  const isGmMarked = beat.predicate_type === 'gm_marked';
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
        <div className="flex items-center gap-2">
          {isAggregate && characterSheetId != null && (
            <ContributeBeatDialog
              beat={beat}
              characterSheetId={characterSheetId}
              currentTotal={aggregateTotal}
            />
          )}
          {isGmMarked && !isResolved && beat.can_mark && <MarkBeatDialog beat={beat} />}
          <BeatOutcomeBadge outcome={outcome} />
        </div>
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
