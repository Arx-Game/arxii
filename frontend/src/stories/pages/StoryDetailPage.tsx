/**
 * StoryDetailPage — player read-only view of a single story.
 *
 * Shows:
 *  1. Story header (title, scope badge, status, breadcrumb)
 *  2. "Change my GM" / "Offer to a GM" CTA (CHARACTER-scope, owned stories only)
 *  3. Current Episode Panel (beats)
 *  4. Story Log timeline
 *  5. Session request status
 */

import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { useStory, useMyActiveStories } from '../queries';
import { ScopeBadge } from '../components/ScopeBadge';
import { StatusBadge } from '../components/StatusBadge';
import { CurrentEpisodePanel } from '../components/CurrentEpisodePanel';
import { StoryLog } from '../components/StoryLog';
import { SessionRequestStatusCard } from '../components/SessionRequestStatusCard';
import { ChangeMyGMDialog } from '../components/ChangeMyGMDialog';

// ---------------------------------------------------------------------------
// Loading skeleton for the header area
// ---------------------------------------------------------------------------

function HeaderSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-48" />
      <Skeleton className="h-5 w-32" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inner page (inside error boundary, receives parsed storyId)
// ---------------------------------------------------------------------------

interface StoryDetailInnerProps {
  storyId: number;
}

function StoryDetailInner({ storyId }: StoryDetailInnerProps) {
  const navigate = useNavigate();

  const { data: story, isLoading: storyLoading } = useStory(storyId);
  const { data: myActive } = useMyActiveStories();

  // Find this story's entry in the my-active dashboard for status/progress info.
  const allEntries = [
    ...(myActive?.character_stories ?? []),
    ...(myActive?.group_stories ?? []),
    ...(myActive?.global_stories ?? []),
  ];
  const activeEntry = allEntries.find((e) => e.story_id === storyId);

  // The "Change my GM" CTA is visible only when:
  //   1. The story is CHARACTER-scope.
  //   2. This story appears in myActive.character_stories — this means the
  //      current user's character is the owner of this story.
  const isOwnedCharacterStory =
    story != null &&
    story.scope === 'character' &&
    (myActive?.character_stories ?? []).some((e) => e.story_id === storyId);

  if (storyLoading) {
    return (
      <div className="space-y-6">
        <HeaderSkeleton />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!story) {
    return (
      <div className="py-16 text-center">
        <p className="text-muted-foreground">Story not found.</p>
        <Button variant="outline" className="mt-4" onClick={() => void navigate('/stories')}>
          Back to My Stories
        </Button>
      </div>
    );
  }

  // Build breadcrumb from active entry if available
  const breadcrumb =
    activeEntry?.chapter_order != null && activeEntry?.episode_order != null
      ? `Chapter ${activeEntry.chapter_order}: ${activeEntry.chapter_title ?? ''} • Episode ${activeEntry.episode_order}: ${activeEntry.current_episode_title ?? ''}`
      : null;

  return (
    <div className="space-y-6">
      {/* Back link */}
      <button
        onClick={() => void navigate('/stories')}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        My Stories
      </button>

      {/* Story header */}
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold">{story.title}</h1>
          <ScopeBadge scope={story.scope ?? 'character'} />
        </div>

        {breadcrumb && <p className="text-sm text-muted-foreground">{breadcrumb}</p>}

        {activeEntry && (
          <StatusBadge status={activeEntry.status} label={activeEntry.status_label} />
        )}

        {/* "Change my GM" / "Offer to a GM" CTA */}
        {isOwnedCharacterStory && <ChangeMyGMDialog story={story} />}
      </header>

      {/* Current episode panel */}
      {activeEntry?.current_episode_id != null ? (
        <CurrentEpisodePanel
          episodeId={activeEntry.current_episode_id}
          characterSheetId={story.character_sheet}
        />
      ) : (
        <section className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">No active episode at this time.</p>
        </section>
      )}

      {/* Session request status (Wave 4 — read-only display) */}
      {activeEntry && <SessionRequestStatusCard activeEntry={activeEntry} />}

      {/* Story log */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Story Log</h2>
        <StoryLog storyId={storyId} />
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function StoryDetailPage() {
  const { id } = useParams<{ id: string }>();
  const parsed = id ? Number(id) : NaN;
  const storyId = Number.isFinite(parsed) && parsed > 0 ? parsed : 0;

  if (storyId === 0) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="py-16 text-center">
          <p className="text-muted-foreground">Story not found.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <ErrorBoundary>
        <StoryDetailInner storyId={storyId} />
      </ErrorBoundary>
    </div>
  );
}
