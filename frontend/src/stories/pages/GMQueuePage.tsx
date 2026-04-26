/**
 * GMQueuePage — Lead GM queue dashboard.
 *
 * Wave 5: read-only display. Shows three sections from GET /api/stories/gm-queue/:
 *   - Episodes ready to run (scope filter)
 *   - AGM claims pending approval
 *   - Assigned session requests
 *
 * Action UIs (resolve episode, mark beat, approve/reject claims, schedule events)
 * come in Wave 6.
 *
 * Permission gating: the endpoint returns 403 for non-GMs. We use a local query
 * with throwOnError: false so we can render a friendly "not a GM" page rather
 * than blowing the error boundary.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Skeleton } from '@/components/ui/skeleton';
import { getGMQueue } from '../api';
import { storiesKeys } from '../queries';
import { EpisodeReadyCard } from '../components/EpisodeReadyCard';
import { PendingClaimRow } from '../components/PendingClaimRow';
import { AssignedSessionRequestRow } from '../components/AssignedSessionRequestRow';
import type { GMQueueEpisodeEntry, StoryScope } from '../types';

// ---------------------------------------------------------------------------
// Scope filter for episodes section
// ---------------------------------------------------------------------------

type ScopeFilter = 'all' | StoryScope;

const EPISODE_FILTER_CHIPS: { value: ScopeFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'character', label: 'Personal' },
  { value: 'group', label: 'Group' },
  { value: 'global', label: 'Global' },
];

// ---------------------------------------------------------------------------
// Skeleton loading placeholder
// ---------------------------------------------------------------------------

function SectionSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3" data-testid="section-skeleton">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="animate-pulse rounded-lg border bg-card p-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-5 w-16" />
          </div>
          <div className="mt-2 flex gap-3">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-24" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section header
// ---------------------------------------------------------------------------

function SectionHeader({ title, count }: { title: string; count?: number }) {
  return (
    <h2 className="text-lg font-semibold text-foreground">
      {title}
      {count !== undefined && (
        <span className="ml-2 text-sm font-normal text-muted-foreground">({count})</span>
      )}
    </h2>
  );
}

// ---------------------------------------------------------------------------
// Not-a-GM page
// ---------------------------------------------------------------------------

function NotGMPage() {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center text-center">
      <h2 className="text-xl font-semibold">Access Denied</h2>
      <p className="mt-2 max-w-md text-muted-foreground">
        You don&apos;t have a GM profile. Contact staff if you should have GM access.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inner page content
// ---------------------------------------------------------------------------

function GMQueueInner() {
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>('all');

  // Use a local query with throwOnError: false so we can inspect the error
  // and show a friendly "not a GM" page on 403 instead of blowing up the
  // error boundary.
  const { data, isLoading, error } = useQuery({
    queryKey: storiesKeys.gmQueue(),
    queryFn: getGMQueue,
    throwOnError: false,
    retry: false,
  });

  // 403 → not a GM
  if (error) {
    const status = (error as Error & { status?: number }).status;
    if (status === 403) {
      return <NotGMPage />;
    }
    // Other errors: re-throw to let the error boundary handle them
    throw error;
  }

  if (isLoading) {
    return (
      <div className="space-y-10">
        <section>
          <SectionHeader title="Episodes Ready to Run" />
          <div className="mt-4">
            <SectionSkeleton rows={3} />
          </div>
        </section>
        <section>
          <SectionHeader title="AGM Claims Pending Approval" />
          <div className="mt-4">
            <SectionSkeleton rows={2} />
          </div>
        </section>
        <section>
          <SectionHeader title="My Session Requests" />
          <div className="mt-4">
            <SectionSkeleton rows={2} />
          </div>
        </section>
      </div>
    );
  }

  const episodes = data?.episodes_ready_to_run ?? [];
  const claims = data?.pending_agm_claims ?? [];
  const sessionRequests = data?.assigned_session_requests ?? [];

  const filteredEpisodes: GMQueueEpisodeEntry[] =
    scopeFilter === 'all' ? episodes : episodes.filter((e) => e.scope === scopeFilter);

  return (
    <div className="space-y-10">
      {/* ------------------------------------------------------------------ */}
      {/* Episodes ready to run                                               */}
      {/* ------------------------------------------------------------------ */}
      <section data-testid="episodes-section">
        <SectionHeader title="Episodes Ready to Run" count={filteredEpisodes.length} />

        {/* Scope filter chips */}
        <div className="mt-3 flex flex-wrap gap-2">
          {EPISODE_FILTER_CHIPS.map((chip) => (
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

        <div className="mt-4 space-y-3">
          {filteredEpisodes.length === 0 ? (
            <p className="py-4 text-muted-foreground">No episodes ready to run right now.</p>
          ) : (
            filteredEpisodes.map((entry) => (
              <EpisodeReadyCard key={`${entry.story_id}-${entry.episode_id}`} entry={entry} />
            ))
          )}
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* AGM claims pending approval                                         */}
      {/* ------------------------------------------------------------------ */}
      <section data-testid="claims-section">
        <SectionHeader title="AGM Claims Pending Approval" count={claims.length} />
        <div className="mt-4 space-y-3">
          {claims.length === 0 ? (
            <p className="py-4 text-muted-foreground">No AGM claims awaiting your approval.</p>
          ) : (
            claims.map((claim) => <PendingClaimRow key={claim.claim_id} claim={claim} />)
          )}
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Assigned session requests                                           */}
      {/* ------------------------------------------------------------------ */}
      <section data-testid="session-requests-section">
        <SectionHeader title="My Session Requests" count={sessionRequests.length} />
        <div className="mt-4 space-y-3">
          {sessionRequests.length === 0 ? (
            <p className="py-4 text-muted-foreground">No session requests assigned to you.</p>
          ) : (
            sessionRequests.map((req) => (
              <AssignedSessionRequestRow key={req.session_request_id} request={req} />
            ))
          )}
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function GMQueuePage() {
  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="mb-8 text-2xl font-bold">GM Queue</h1>
      <GMQueueInner />
    </div>
  );
}
