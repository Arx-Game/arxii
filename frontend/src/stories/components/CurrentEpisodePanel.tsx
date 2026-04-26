/**
 * CurrentEpisodePanel — shows the current episode header and beat list.
 */

import { Skeleton } from '@/components/ui/skeleton';
import { useEpisode } from '../queries';
import { BeatList } from './BeatList';

interface CurrentEpisodePanelProps {
  episodeId: number;
}

export function CurrentEpisodePanel({ episodeId }: CurrentEpisodePanelProps) {
  const { data: episode, isLoading } = useEpisode(episodeId);

  if (isLoading) {
    return (
      <section className="space-y-3 rounded-lg border bg-card p-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </section>
    );
  }

  if (!episode) {
    return (
      <section className="rounded-lg border bg-card p-4">
        <p className="text-sm text-muted-foreground">Episode not found.</p>
      </section>
    );
  }

  return (
    <section className="space-y-4 rounded-lg border bg-card p-4">
      <div>
        <h2 className="text-lg font-semibold">Current Episode</h2>
        <p className="text-base font-medium">{episode.title}</p>
        {episode.description && (
          <p className="mt-1 text-sm text-muted-foreground">{episode.description}</p>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Beats
        </h3>
        <BeatList episodeId={episodeId} />
      </div>
    </section>
  );
}
