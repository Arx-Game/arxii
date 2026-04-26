/**
 * MyActiveStoriesPage — player-facing list of all active stories.
 *
 * Shows three scope groups (Personal / Group / Global) with filter chips
 * to narrow down by scope. Each story is rendered as a StoryCard.
 */

import { useState } from 'react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { useMyActiveStories } from '../queries';
import { StoryCard } from '../components/StoryCard';
import type { MyActiveStoryEntry, StoryScope } from '../types';

// ---------------------------------------------------------------------------
// Filter state
// ---------------------------------------------------------------------------

type ScopeFilter = 'all' | StoryScope;

const FILTER_CHIPS: { value: ScopeFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'character', label: 'Personal' },
  { value: 'group', label: 'Group' },
  { value: 'global', label: 'Global' },
];

// ---------------------------------------------------------------------------
// Empty state messages
// ---------------------------------------------------------------------------

const EMPTY_MESSAGES: Record<ScopeFilter, string> = {
  all: "You don't have any active stories yet.",
  character:
    'No personal stories yet. Apply for a roster character or wait for staff to create one.',
  group: "You're not in any group stories yet. Join a covenant or table to participate.",
  global: 'No metaplot stories active right now.',
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SectionHeader({ title }: { title: string }) {
  return <h2 className="text-lg font-semibold text-muted-foreground">{title}</h2>;
}

function StorySectionList({ entries, title }: { entries: MyActiveStoryEntry[]; title: string }) {
  if (entries.length === 0) return null;
  return (
    <section className="space-y-2">
      <SectionHeader title={title} />
      {entries.map((entry) => (
        <StoryCard key={entry.story_id} entry={entry} />
      ))}
    </section>
  );
}

function LoadingSkeletons() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="animate-pulse rounded-lg border bg-card p-4"
          data-testid="story-card-skeleton"
        >
          <div className="flex items-center gap-3">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-5 w-16" />
          </div>
          <div className="mt-2 flex gap-3">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-20" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inner page (inside error boundary)
// ---------------------------------------------------------------------------

function MyActiveStoriesInner() {
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>('all');
  const { data, isLoading } = useMyActiveStories();

  if (isLoading) return <LoadingSkeletons />;

  const characterStories = data?.character_stories ?? [];
  const groupStories = data?.group_stories ?? [];
  const globalStories = data?.global_stories ?? [];

  const filteredByScope = (entries: MyActiveStoryEntry[], scope: StoryScope) =>
    scopeFilter === 'all' || scopeFilter === scope ? entries : [];

  const visibleCharacter = filteredByScope(characterStories, 'character');
  const visibleGroup = filteredByScope(groupStories, 'group');
  const visibleGlobal = filteredByScope(globalStories, 'global');

  const hasAny = visibleCharacter.length > 0 || visibleGroup.length > 0 || visibleGlobal.length > 0;

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
          <StorySectionList entries={visibleCharacter} title="Personal Stories" />
          <StorySectionList entries={visibleGroup} title="Group Stories" />
          <StorySectionList entries={visibleGlobal} title="Global Stories" />
        </div>
      ) : (
        <div className="space-y-2">
          {[...visibleCharacter, ...visibleGroup, ...visibleGlobal].map((entry) => (
            <StoryCard key={entry.story_id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function MyActiveStoriesPage() {
  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">My Stories</h1>
      <ErrorBoundary>
        <MyActiveStoriesInner />
      </ErrorBoundary>
    </div>
  );
}
