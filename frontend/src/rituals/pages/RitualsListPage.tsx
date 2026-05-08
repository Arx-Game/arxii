/**
 * RitualsListPage — browse and perform available rituals.
 *
 * Split into two sections:
 *   1. "Authored by you" — rituals where author_account matches the current account id.
 *      These are SCENE_ACTION anima rituals the player has personalised.
 *   2. "Known rituals" — all other rituals the character has knowledge of.
 *
 * Backend gap (Phase 9): The RitualSerializer does not expose `author_account_id`,
 * so the authored/known split currently falls back to checking
 * execution_kind === 'SCENE_ACTION' as a proxy. When Phase 10 adds
 * `author_account_id` to the serializer, replace the proxy check with a
 * proper account-id comparison.
 *
 * The active character's id == CharacterSheet pk (OneToOne primary_key=True on ObjectDB).
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
// Section header
// ---------------------------------------------------------------------------

function SectionHeader({ title }: { title: string }) {
  return <h2 className="mb-3 text-lg font-semibold text-foreground">{title}</h2>;
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
  const currentAccountId = account?.id ?? null;

  if (isLoading) return <LoadingSkeletons />;

  // No character: tell the player they need one.
  if (!characterSheetId) {
    return (
      <p className="py-8 text-center text-muted-foreground">
        You need an active character to perform rituals.
      </p>
    );
  }

  const allRituals = (data?.results ?? []) as RitualWithSchema[];

  if (allRituals.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground">
        No rituals available for your character at this time.
      </p>
    );
  }

  // Partition rituals: SCENE_ACTION execution_kind is a proxy for "authored by you"
  // until Phase 10 backend adds author_account_id to the serializer.
  // When that lands, replace this with:
  //   const authoredRituals = allRituals.filter(r => r.author_account_id === currentAccountId);
  //   const knownRituals = allRituals.filter(r => r.author_account_id !== currentAccountId);
  const authoredRituals = allRituals.filter((r) => (r.execution_kind as string) === 'SCENE_ACTION');
  const knownRituals = allRituals.filter((r) => (r.execution_kind as string) !== 'SCENE_ACTION');

  const hasSections = authoredRituals.length > 0 && knownRituals.length > 0;

  return (
    <div className="space-y-8">
      {/* Authored by you — SCENE_ACTION anima rituals */}
      {authoredRituals.length > 0 && (
        <section data-testid="authored-rituals-section">
          {hasSections && <SectionHeader title="Authored by you" />}
          <div className="space-y-3">
            {authoredRituals.map((ritual) => (
              <RitualCard
                key={ritual.id}
                ritual={ritual}
                characterSheetId={characterSheetId}
                currentAccountId={currentAccountId}
                // author_account_id not yet in serializer — Phase 10 gap.
                // For now, pass currentAccountId so edit button is visible to owner.
                authorAccountId={currentAccountId}
              />
            ))}
          </div>
        </section>
      )}

      {/* Known rituals — everything else */}
      {knownRituals.length > 0 && (
        <section data-testid="known-rituals-section">
          {hasSections && <SectionHeader title="Known rituals" />}
          <div className="space-y-3">
            {knownRituals.map((ritual) => (
              <RitualCard
                key={ritual.id}
                ritual={ritual}
                characterSheetId={characterSheetId}
                currentAccountId={currentAccountId}
              />
            ))}
          </div>
        </section>
      )}
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
