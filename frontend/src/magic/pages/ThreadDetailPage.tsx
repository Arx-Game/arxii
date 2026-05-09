/**
 * ThreadDetailPage — detail view for a single Thread at /threads/:id.
 *
 * Layout:
 *   Breadcrumb → Threads / {thread.name}
 *   Title with [Edit] button (opens ThreadRenameDialog)
 *   Description block
 *   Stats card: level, developed_points, effective_cap, anchor_cap, path_cap
 *   ImbuePanel (if not retired and level < effective_cap or cap unavailable)
 *   XPLockBoundaryPanel (prospect from hub summary for this thread)
 *   PullEffectPreview
 *   Footer: [Retire Thread] (opens ThreadRetireDialog, destructive variant)
 */
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { useCharacterResonances, useThread, useThreadHubSummary } from '../queries';
import { useAccountProgressionQuery } from '@/progression/queries';
import { ImbuePanel } from '../components/threads/ImbuePanel';
import { XPLockBoundaryPanel } from '../components/threads/XPLockBoundaryPanel';
import { PullEffectPreview } from '../components/threads/PullEffectPreview';
import { ThreadRenameDialog } from '../components/threads/ThreadRenameDialog';
import { ThreadRetireDialog } from '../components/threads/ThreadRetireDialog';

export function ThreadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const threadId = Number(id ?? '0');

  const { data: thread, isLoading: threadLoading } = useThread(threadId);
  const { data: summary, isLoading: summaryLoading } = useThreadHubSummary();
  const { data: characterResonances } = useCharacterResonances();
  const { data: progressionData } = useAccountProgressionQuery();

  const [renameOpen, setRenameOpen] = useState(false);
  const [retireOpen, setRetireOpen] = useState(false);

  const isLoading = threadLoading || summaryLoading;

  if (isLoading) {
    return (
      <div className="container mx-auto space-y-6 px-4 py-8">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-32 w-full rounded-lg" />
      </div>
    );
  }

  if (!thread) {
    return (
      <div className="container mx-auto px-4 py-8">
        <p className="text-muted-foreground">Thread not found.</p>
        <Link to="/threads" className="mt-4 inline-block text-sm underline">
          Back to Threads
        </Link>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Derive display data
  // ---------------------------------------------------------------------------

  const displayName = thread.name.trim() || '(unnamed)';
  const displayLevel = thread.level / 10;

  // Find the resonance balance for this thread's resonance from hub summary.
  const resonanceBalance = summary?.balances.find((b) => b.resonance_id === thread.resonance);
  const spendableBalance = resonanceBalance?.balance ?? 0;

  // Find the character sheet ID for this thread from character resonances.
  // The thread.owner is the character_sheet PK.
  const characterSheetId = thread.owner;

  // Find this thread's XP-lock prospect from summary.
  const prospect = summary?.near_xp_lock_thread_ids.find((p) => p.thread_id === thread.id) ?? null;

  // Account available XP from progression data.
  // TODO: expose via a dedicated endpoint if progression data is not loaded.
  const accountAvailableXP = progressionData?.xp?.current_available ?? 0;

  // Find resonance name from character resonances (fallback to resonance_name from thread).
  const characterResonance = characterResonances?.find((cr) => cr.resonance === thread.resonance);
  const resonanceName = characterResonance?.resonance_name ?? thread.resonance_name;

  // Determine if the thread is retired.
  const isRetired = thread.retired_at !== null;

  // Determine if ImbuePanel should render.
  // Render if not retired and level is below effective cap (or cap fields unavailable).
  const belowCap =
    thread.effective_cap === null || thread.effective_cap === undefined
      ? true
      : thread.level < thread.effective_cap;
  const showImbuePanel = !isRetired && belowCap;

  return (
    <div className="container mx-auto space-y-6 px-4 py-8">
      {/* Breadcrumb */}
      <nav className="text-sm text-muted-foreground" aria-label="Breadcrumb">
        <Link to="/threads" className="underline hover:text-foreground">
          Threads
        </Link>
        <span className="mx-2">/</span>
        <span className="text-foreground">{displayName}</span>
      </nav>

      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold" data-testid="thread-detail-title">
          {displayName}
        </h1>
        {isRetired && (
          <span className="rounded bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            Retired
          </span>
        )}
        {!isRetired && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setRenameOpen(true)}
            data-testid="thread-edit-button"
          >
            Edit
          </Button>
        )}
      </div>

      {/* Description */}
      {thread.description ? (
        <p className="text-muted-foreground" data-testid="thread-description">
          {thread.description}
        </p>
      ) : (
        <p className="text-sm italic text-muted-foreground" data-testid="thread-description-empty">
          No description yet.
        </p>
      )}

      {/* Stats card */}
      <div className="rounded-lg border bg-card p-4" data-testid="thread-stats-card">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Thread Stats
        </h2>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-muted-foreground">Level</dt>
            <dd className="font-medium tabular-nums" data-testid="thread-stat-level">
              {displayLevel}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Developed Points</dt>
            <dd className="font-medium tabular-nums" data-testid="thread-stat-dp">
              {thread.developed_points}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Resonance</dt>
            <dd className="font-medium" data-testid="thread-stat-resonance">
              {resonanceName}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Anchor</dt>
            <dd className="font-medium" data-testid="thread-stat-anchor">
              {thread.target_kind}
            </dd>
          </div>
          {thread.path_cap !== undefined && thread.path_cap !== null && (
            <div>
              <dt className="text-muted-foreground">Path Cap</dt>
              <dd className="font-medium tabular-nums" data-testid="thread-stat-path-cap">
                {thread.path_cap / 10}
              </dd>
            </div>
          )}
          {thread.anchor_cap !== undefined && thread.anchor_cap !== null && (
            <div>
              <dt className="text-muted-foreground">Anchor Cap</dt>
              <dd className="font-medium tabular-nums" data-testid="thread-stat-anchor-cap">
                {thread.anchor_cap / 10}
              </dd>
            </div>
          )}
          {thread.effective_cap !== undefined && thread.effective_cap !== null && (
            <div>
              <dt className="text-muted-foreground">Effective Cap</dt>
              <dd className="font-medium tabular-nums" data-testid="thread-stat-effective-cap">
                {thread.effective_cap / 10}
              </dd>
            </div>
          )}
        </dl>
      </div>

      {/* ImbuePanel */}
      {showImbuePanel && (
        <ImbuePanel
          thread={thread}
          balance={spendableBalance}
          characterSheetId={characterSheetId}
        />
      )}

      {/* XPLockBoundaryPanel */}
      <XPLockBoundaryPanel
        thread={thread}
        prospect={prospect}
        accountAvailableXP={accountAvailableXP}
      />

      {/* PullEffectPreview */}
      <PullEffectPreview thread={thread} />

      {/* Footer: retire button */}
      {!isRetired && (
        <div className="border-t pt-4">
          <Button
            type="button"
            variant="destructive"
            onClick={() => setRetireOpen(true)}
            data-testid="thread-retire-button"
          >
            Retire Thread
          </Button>
        </div>
      )}

      {/* Dialogs */}
      {renameOpen && (
        <ThreadRenameDialog thread={thread} open={renameOpen} onOpenChange={setRenameOpen} />
      )}
      {retireOpen && (
        <ThreadRetireDialog thread={thread} open={retireOpen} onOpenChange={setRetireOpen} />
      )}
    </div>
  );
}
