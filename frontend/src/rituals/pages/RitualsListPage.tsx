/**
 * RitualsListPage — browse and perform available rituals.
 *
 * Reads the list from useRituals() and the active character from the auth
 * Redux slice. The first entry in `account.available_characters` is used as
 * the performing character; its `id` is the ObjectDB pk which equals the
 * CharacterSheet pk (OneToOne with primary_key=True).
 *
 * If the player has no available character, a friendly empty state is shown
 * and the rituals query is still fired (the page is read-only until a
 * character is selected). The Perform button is hidden in that case.
 */

import { useSelector } from 'react-redux';
import type { RootState } from '@/store/store';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { useRituals } from '@/rituals/queries';
import { RitualCard } from '../components/RitualCard';
import type { RitualWithSchema } from '../types';

// ---------------------------------------------------------------------------
// Loading skeletons
// ---------------------------------------------------------------------------

function RitualCardSkeleton() {
  return (
    <div className="animate-pulse rounded-lg border bg-card p-4" data-testid="ritual-card-skeleton">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 space-y-2">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
        <Skeleton className="h-8 w-16 shrink-0" />
      </div>
    </div>
  );
}

function LoadingSkeletons() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <RitualCardSkeleton key={i} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inner page (inside error boundary)
// ---------------------------------------------------------------------------

function RitualsListInner() {
  const account = useSelector((state: RootState) => state.auth.account);

  const { data, isLoading } = useRituals();

  // The currently puppeted character (has currently_puppeted_in_session: true).
  // Its id == CharacterSheet pk (OneToOne primary_key=True on ObjectDB).
  const activeCharacter =
    account?.available_characters?.find((c) => c.currently_puppeted_in_session) ?? null;
  const characterSheetId = activeCharacter?.id ?? null;

  if (isLoading) return <LoadingSkeletons />;

  // No character: tell the player they need one.
  if (!characterSheetId) {
    return (
      <p className="py-8 text-center text-muted-foreground">
        You need an active character to perform rituals.
      </p>
    );
  }

  const rituals = data?.results ?? [];

  if (rituals.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground">
        No rituals available for your character at this time.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {rituals.map((ritual) => (
        <RitualCard
          key={ritual.id}
          ritual={ritual as RitualWithSchema}
          characterSheetId={characterSheetId}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function RitualsListPage() {
  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <h1 className="mb-6 text-2xl font-bold">Rituals</h1>
      <ErrorBoundary>
        <RitualsListInner />
      </ErrorBoundary>
    </div>
  );
}
