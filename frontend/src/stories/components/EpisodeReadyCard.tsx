/**
 * EpisodeReadyCard — single row for an episode-ready-to-run entry in GMQueuePage.
 *
 * Wave 6: adds the "Resolve" action dialog inline on the card.
 */

import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { ScopeBadge } from './ScopeBadge';
import { ResolveEpisodeDialog } from './ResolveEpisodeDialog';
import type { GMQueueEpisodeEntry } from '../types';

interface EpisodeReadyCardProps {
  entry: GMQueueEpisodeEntry;
}

function transitionSummary(transitions: GMQueueEpisodeEntry['eligible_transitions']): string {
  if (transitions.length === 0) return 'No eligible transitions';
  const autoCount = transitions.filter((t) => t.mode === 'AUTO').length;
  const gmCount = transitions.length - autoCount;
  const parts: string[] = [];
  if (autoCount > 0) parts.push(`${autoCount} AUTO`);
  if (gmCount > 0) parts.push(`${gmCount} GM_CHOICE`);
  return `${transitions.length} transition${transitions.length !== 1 ? 's' : ''} (${parts.join(', ')})`;
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
          <ResolveEpisodeDialog entry={entry} />
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
