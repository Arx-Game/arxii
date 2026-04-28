/**
 * MuteSettingsPage — list of muted stories with per-row Unmute button.
 *
 * Lets users review what they have muted and remove mutes selectively.
 *
 * Wave 11 will register the route at /profile/mute-settings.
 */

import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useStoryMutes, useUnmuteStory } from '../queries';
import type { UserStoryMute } from '../types';

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function LoadingSkeletons() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="animate-pulse rounded-lg border bg-card p-4"
          data-testid="mute-row-skeleton"
        >
          <div className="flex items-center justify-between">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-8 w-20" />
          </div>
        </div>
      ))}
    </div>
  );
}

interface MuteRowProps {
  mute: UserStoryMute;
}

function MuteRow({ mute }: MuteRowProps) {
  const unmuteStory = useUnmuteStory();

  return (
    <div
      className="flex items-center justify-between rounded-lg border bg-card p-4"
      data-testid="mute-row"
    >
      <div className="space-y-0.5">
        <p className="font-medium">Story #{mute.story}</p>
        <p className="text-xs text-muted-foreground">
          Muted {new Date(mute.muted_at).toLocaleDateString()}
        </p>
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={() => unmuteStory.mutate(mute.id)}
        disabled={unmuteStory.isPending}
        data-testid="unmute-button"
      >
        Unmute
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inner page (inside error boundary)
// ---------------------------------------------------------------------------

function MuteSettingsInner() {
  const { data, isLoading } = useStoryMutes();

  if (isLoading) return <LoadingSkeletons />;

  const mutes = data?.results ?? [];

  if (mutes.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground" data-testid="mute-empty-state">
        You haven&apos;t muted any stories. Real-time updates will arrive for all your active
        stories.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {mutes.map((mute) => (
        <MuteRow key={mute.id} mute={mute} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function MuteSettingsPage() {
  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <h1 className="mb-2 text-2xl font-bold">Muted Stories</h1>
      <p className="mb-6 text-muted-foreground">
        Muted stories still appear in your dashboard — real-time notifications are suppressed.
      </p>
      <ErrorBoundary>
        <MuteSettingsInner />
      </ErrorBoundary>
    </div>
  );
}
