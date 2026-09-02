/**
 * EpisodeReadyCard - single row for an episode-ready-to-run entry in GMQueuePage.
 *
 * #3565: GM-choice transitions are retired - every transition now fires
 * automatically off its routing predicate (beat outcome / scenario option
 * key), so there is no eligible-set picker left for a GM to choose from.
 * The old "Resolve" dialog is gone, but the Lead GM's ADVANCE gesture is
 * not: resolve_episode() is only ever called from POST
 * /api/episodes/{id}/resolve/ (plus the telnet action), so the web GM
 * queue still needs a trigger for it. "Advance episode" fires the lowest-
 * order eligible transition server-side (or the frontier, when none are
 * eligible) - no picker, no transition list.
 */

import { toast } from 'sonner';
import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ScopeBadge } from './ScopeBadge';
import { useResolveEpisode } from '../queries';
import type { GMQueueEpisodeEntry } from '../types';

interface EpisodeReadyCardProps {
  entry: GMQueueEpisodeEntry;
}

function transitionSummary(transitions: GMQueueEpisodeEntry['eligible_transitions']): string {
  const n = transitions.length;
  if (n === 0) return 'No eligible transitions';
  return `${n} transition${n !== 1 ? 's' : ''}`;
}

function handleAdvanceError(err: unknown) {
  if (err && typeof err === 'object' && 'response' in err) {
    const response = (err as { response?: Response }).response;
    if (response) {
      void response
        .json()
        .then((data: unknown) => {
          const drf = data as { detail?: string; non_field_errors?: string[] };
          toast.error(drf.detail ?? drf.non_field_errors?.join(' ') ?? 'Failed to advance episode');
        })
        .catch(() => toast.error('Failed to advance episode'));
      return;
    }
  }
  toast.error(err instanceof Error ? err.message : 'Failed to advance episode');
}

export function EpisodeReadyCard({ entry }: EpisodeReadyCardProps) {
  const resolveMutation = useResolveEpisode();
  const hasTransitions = entry.eligible_transitions.length > 0;

  function handleAdvance() {
    resolveMutation.mutate(
      {
        episodeId: entry.episode_id,
        storyId: entry.story_id,
        progress_id: entry.progress_id,
      },
      {
        onSuccess: () => toast.success('Episode advanced'),
        onError: handleAdvanceError,
      }
    );
  }

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
          {hasTransitions && (
            <Button
              type="button"
              size="sm"
              onClick={handleAdvance}
              disabled={resolveMutation.isPending}
              data-testid="advance-episode-btn"
            >
              {resolveMutation.isPending ? 'Advancing…' : 'Advance episode'}
            </Button>
          )}
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
