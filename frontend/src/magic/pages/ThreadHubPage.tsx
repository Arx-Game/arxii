import { Link, useNavigate } from 'react-router-dom';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { useThreads, useThreadHubSummary, useCharacterResonances } from '../queries';
import { ResonanceBalanceCard } from '../components/threads/ResonanceBalanceCard';
import { ThreadCard } from '../components/threads/ThreadCard';
import type { Thread, TargetKind } from '../types';

/**
 * Thread Hub page at /threads.
 *
 * Shows the player's resonance balances and thread list grouped by target_kind.
 * Threads are clickable — navigates to /threads/:id (route ships in Task 16).
 * The "Weave New" button is a stub placeholder (TODO Task 17: mount wizard modal).
 */
export function ThreadHubPage() {
  const navigate = useNavigate();
  const { data: threadsData, isLoading: threadsLoading } = useThreads();
  const { data: summary, isLoading: summaryLoading } = useThreadHubSummary();
  const { data: characterResonances, isLoading: resonancesLoading } = useCharacterResonances();

  const threads = threadsData?.results ?? [];
  const balancesLoading = summaryLoading || resonancesLoading;

  // Group threads by target_kind
  const threadsByKind = threads.reduce<Record<string, Thread[]>>((acc, thread) => {
    const kind = thread.target_kind;
    if (!acc[kind]) {
      acc[kind] = [];
    }
    acc[kind].push(thread);
    return acc;
  }, {});

  const nonEmptyKinds = Object.keys(threadsByKind) as TargetKind[];

  const handleThreadClick = (thread: Thread) => {
    // TODO Task 16: thread detail page ships here — /threads/:id will resolve to ThreadDetailPage
    void navigate(`/threads/${thread.id}`);
  };

  const handleWeaveNew = () => {
    // TODO Task 17: open the WeaveThreadWizard modal here
  };

  return (
    <div className="container mx-auto space-y-8 px-4 py-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Your Threads</h1>
        <div className="flex gap-2">
          <Button onClick={handleWeaveNew} variant="default">
            Weave New
          </Button>
          <Button asChild variant="outline">
            <Link to="/threads/teaching">Browse Teachers</Link>
          </Button>
        </div>
      </div>

      {/* Resonance balances row */}
      <section aria-label="Resonance balances">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Resonance Balances
        </h2>
        {balancesLoading ? (
          <div className="flex flex-wrap gap-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24 w-32 rounded-lg" />
            ))}
          </div>
        ) : !summary || summary.balances.length === 0 ? (
          <p className="text-sm text-muted-foreground">No resonances claimed yet.</p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {summary.balances.map((balance) => {
              const characterResonance = characterResonances?.find(
                (cr) => cr.resonance === balance.resonance_id
              );
              return (
                <ResonanceBalanceCard
                  key={balance.resonance_id}
                  balance={balance}
                  characterResonance={characterResonance}
                />
              );
            })}
          </div>
        )}
      </section>

      {/* Thread list grouped by target_kind */}
      <section aria-label="Threads">
        {threadsLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-20 w-full rounded-lg" />
            ))}
          </div>
        ) : threads.length === 0 ? (
          <div className="rounded-lg border border-dashed px-6 py-12 text-center">
            <p className="text-muted-foreground">
              You have no threads yet &mdash; weave one with{' '}
              <button
                type="button"
                className="font-medium underline underline-offset-2"
                onClick={handleWeaveNew}
              >
                Weave New
              </button>
              .
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {nonEmptyKinds.map((kind) => (
              <div key={kind}>
                <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  {kind}
                </h2>
                <div className="space-y-2">
                  {threadsByKind[kind].map((thread) =>
                    summary ? (
                      <ThreadCard
                        key={thread.id}
                        thread={thread}
                        summary={summary}
                        onClick={handleThreadClick}
                      />
                    ) : null
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
