/**
 * BrowseStoriesPage — public directory of all stories the current user can see.
 *
 * Shows stories returned by GET /api/stories/ (backend-scoped per Wave 1).
 * Filter chips narrow by scope. Stories are grouped by scope under "All Visible".
 *
 * Wave 11 will register the route at /stories/browse.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useBrowseStories } from '../queries';
import { ScopeBadge } from '../components/ScopeBadge';
import type { StoryList, StoryScope } from '../types';

// ---------------------------------------------------------------------------
// Filter chips
// ---------------------------------------------------------------------------

type ScopeFilter = 'all' | StoryScope;

const FILTER_CHIPS: { value: ScopeFilter; label: string }[] = [
  { value: 'all', label: 'All Visible' },
  { value: 'character', label: 'Personal' },
  { value: 'group', label: 'Group' },
  { value: 'global', label: 'Global' },
];

const EMPTY_MESSAGES: Record<ScopeFilter, string> = {
  all: 'No stories are visible to you right now.',
  character: 'No personal stories visible.',
  group: 'No group stories visible.',
  global: 'No global metaplot stories active right now.',
};

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
          data-testid="browse-story-skeleton"
        >
          <div className="flex items-center gap-3">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-5 w-16" />
          </div>
          <div className="mt-2">
            <Skeleton className="h-4 w-72" />
          </div>
        </div>
      ))}
    </div>
  );
}

interface StoryRowProps {
  story: StoryList;
}

function StoryRow({ story }: StoryRowProps) {
  const navigate = useNavigate();
  const scope = story.scope ?? 'character';
  const isCharacterScope = scope === 'character';

  const ctaLabel = isCharacterScope ? 'Open' : 'Browse';

  return (
    <div
      className="flex flex-col gap-2 rounded-lg border bg-card p-4 sm:flex-row sm:items-start sm:justify-between"
      data-testid="browse-story-row"
    >
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">{story.title}</span>
          <ScopeBadge scope={scope as StoryScope} />
        </div>
        <p className="text-xs text-muted-foreground">
          {story.participants_count} participant{story.participants_count !== 1 ? 's' : ''}
        </p>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="shrink-0"
        onClick={() => void navigate(`/stories/${story.id}`)}
      >
        {ctaLabel}
      </Button>
    </div>
  );
}

interface StorySectionProps {
  title: string;
  stories: StoryList[];
}

function StorySection({ title, stories }: StorySectionProps) {
  if (stories.length === 0) return null;
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold text-muted-foreground">{title}</h2>
      {stories.map((s) => (
        <StoryRow key={s.id} story={s} />
      ))}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Inner page (inside error boundary)
// ---------------------------------------------------------------------------

function BrowseStoriesInner() {
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>('all');
  // When a specific scope chip is selected, pass it as a query param.
  // When 'all', no scope filter — backend returns everything visible.
  const { data, isLoading } = useBrowseStories(scopeFilter === 'all' ? undefined : scopeFilter);

  if (isLoading) return <LoadingSkeletons />;

  const allStories = data?.results ?? [];

  // For "All Visible" — group by scope
  const byScope = (s: StoryScope) => allStories.filter((story) => story.scope === s);
  const characterStories = byScope('character');
  const groupStories = byScope('group');
  const globalStories = byScope('global');

  const hasAny = allStories.length > 0;

  return (
    <div className="space-y-6">
      {/* Filter chips */}
      <div className="flex flex-wrap gap-2">
        {FILTER_CHIPS.map((chip) => (
          <button
            key={chip.value}
            onClick={() => setScopeFilter(chip.value)}
            className={`rounded-full border px-3 py-1 text-sm font-medium transition-colors ${
              scopeFilter === chip.value
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border bg-background hover:bg-accent'
            }`}
          >
            {chip.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {!hasAny ? (
        <p className="py-8 text-center text-muted-foreground">{EMPTY_MESSAGES[scopeFilter]}</p>
      ) : scopeFilter === 'all' ? (
        <div className="space-y-6">
          <StorySection title="Personal Stories" stories={characterStories} />
          <StorySection title="Group Stories" stories={groupStories} />
          <StorySection title="Global Stories" stories={globalStories} />
        </div>
      ) : (
        <div className="space-y-2">
          {allStories.map((s) => (
            <StoryRow key={s.id} story={s} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function BrowseStoriesPage() {
  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">Browse Stories</h1>
      <ErrorBoundary>
        <BrowseStoriesInner />
      </ErrorBoundary>
    </div>
  );
}
