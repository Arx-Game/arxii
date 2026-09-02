/**
 * EpisodeReadyCard — single row for an episode-ready-to-run entry in GMQueuePage.
 *
 * #3565: GM-choice transitions are retired — every transition now fires
 * automatically off its routing predicate (beat outcome / scenario option
 * key), so there is nothing left for a GM to pick from an eligible set. The
 * "Resolve" dialog is gone; the frontier "author the next node" (adding a
 * beat/transition in the author tree) is the only remaining GM action.
 */

import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { ScopeBadge } from './ScopeBadge';
import type { GMQueueEpisodeEntry } from '../types';

interface EpisodeReadyCardProps {
  entry: GMQueueEpisodeEntry;
}

function transitionSummary(transitions: GMQueueEpisodeEntry['eligible_transitions']): string {
  const n = transitions.length;
  if (n === 0) return 'No eligible transitions';
  return `${n} transition${n !== 1 ? 's' : ''}`;
}

export function EpisodeReadyCard({ entry }: EpisodeReadyCardProps) {
  return (
    <Card data-testid="episode-ready-card">
      <CardContent className="py-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-base font-semibold">{entry.story_title}</span>
          <ScopeBadge scope={entry.scope} />
        </div>

        <p className="mt-1 text-sm text-muted-foreground">{entry.episode_title}</p>

        <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
          <span>{transitionSummary(entry.eligible_transitions)}</span>
          {entry.open_session_request_id !== null && (
            <span className="text-blue-600 dark:text-blue-400">Session request open</span>
          )}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Link
            to={`/stories/${entry.story_id}`}
            className="text-sm font-medium text-primary underline-offset-4 hover:underline"
          >
            Open story
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
