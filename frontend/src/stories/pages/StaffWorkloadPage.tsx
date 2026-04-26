/**
 * StaffWorkloadPage — cross-story staff workload dashboard.
 *
 * Wave 8: read-only display + Expire Overdue Beats action.
 * Surfaces GET /api/stories/staff-workload/ (staff-only, IsAdminUser).
 *
 * Layout (top to bottom):
 *   1. Top-line counts (4 stat cards)
 *   2. Counts by scope
 *   3. Per-GM queue depth (sortable table)
 *   4. Stale stories (sortable table, days_stale desc)
 *   5. Stories at frontier (table with scope badge)
 *   6. Manual actions (Expire Overdue Beats)
 *
 * Permission gating: the endpoint 403s for non-staff. throwOnError: false lets
 * us render a friendly "access denied" page rather than blowing the error
 * boundary. Same pattern as GMQueuePage.
 *
 * Route-level StaffRoute wrapper goes in Wave 11.
 */

import { useQuery } from '@tanstack/react-query';
import { Skeleton } from '@/components/ui/skeleton';
import { getStaffWorkload } from '../api';
import { storiesKeys } from '../queries';
import { WorkloadStatCard } from '../components/WorkloadStatCard';
import { PerGMQueueTable } from '../components/PerGMQueueTable';
import { StaleStoriesTable } from '../components/StaleStoriesTable';
import { FrontierStoriesTable } from '../components/FrontierStoriesTable';
import { ExpireBeatsButton } from '../components/ExpireBeatsButton';
import type { StaffWorkloadResponse } from '../types';

// ---------------------------------------------------------------------------
// Skeleton loading state
// ---------------------------------------------------------------------------

function StatCardSkeleton() {
  return (
    <div className="animate-pulse rounded-lg border bg-card p-6">
      <Skeleton className="mx-auto h-10 w-16" />
      <Skeleton className="mx-auto mt-3 h-4 w-28" />
    </div>
  );
}

function TableSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2" data-testid="table-skeleton">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex animate-pulse gap-4 border-b pb-2">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-16" />
        </div>
      ))}
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-10" data-testid="workload-loading">
      {/* Top-line cards */}
      <section>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
        </div>
      </section>

      {/* Counts by scope */}
      <section>
        <Skeleton className="mb-3 h-5 w-36" />
        <div className="flex gap-6">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-4 w-20" />
        </div>
      </section>

      {/* Tables */}
      {(['Per-GM Queue Depth', 'Stale Stories', 'Stories at Frontier'] as const).map((title) => (
        <section key={title}>
          <Skeleton className="mb-4 h-6 w-48" />
          <TableSkeleton rows={3} />
        </section>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Access denied fallback
// ---------------------------------------------------------------------------

function AccessDeniedPage() {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center text-center">
      <h2 className="text-xl font-semibold">Access Denied</h2>
      <p className="mt-2 max-w-md text-muted-foreground">
        This page is only accessible to staff. Contact an administrator if you should have access.
      </p>
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
// Counts-by-scope strip
// ---------------------------------------------------------------------------

const SCOPE_ORDER = ['character', 'group', 'global'] as const;
const SCOPE_LABELS: Record<string, string> = {
  character: 'Character',
  group: 'Group',
  global: 'Global',
};

interface ScopesStripProps {
  counts: Record<string, number>;
}

function ScopesStrip({ counts }: ScopesStripProps) {
  const allScopes = [
    ...SCOPE_ORDER.filter((s) => s in counts),
    ...Object.keys(counts).filter((s) => !SCOPE_ORDER.includes(s as (typeof SCOPE_ORDER)[number])),
  ];

  if (allScopes.length === 0) {
    return <p className="text-sm text-muted-foreground">No active stories by scope.</p>;
  }

  return (
    <dl className="flex flex-wrap gap-6" data-testid="scope-counts">
      {allScopes.map((scope) => (
        <div key={scope} className="flex items-baseline gap-1">
          <dt className="text-sm text-muted-foreground">{SCOPE_LABELS[scope] ?? scope}:</dt>
          <dd className="text-sm font-semibold tabular-nums">{counts[scope] ?? 0}</dd>
        </div>
      ))}
    </dl>
  );
}

// ---------------------------------------------------------------------------
// Inner content (data loaded)
// ---------------------------------------------------------------------------

function StaffWorkloadInner({ data }: { data: StaffWorkloadResponse }) {
  return (
    <div className="space-y-10">
      {/* ------------------------------------------------------------------ */}
      {/* Top-line counts                                                      */}
      {/* ------------------------------------------------------------------ */}
      <section data-testid="stat-cards-section">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <WorkloadStatCard
            label="Pending AGM Claims"
            value={data.pending_agm_claims_count}
            valueClassName={data.pending_agm_claims_count > 0 ? 'text-amber-500' : ''}
          />
          <WorkloadStatCard
            label="Open Session Requests"
            value={data.open_session_requests_count}
          />
          <WorkloadStatCard
            label="Stale Stories (>14d)"
            value={data.stale_stories.length}
            valueClassName={data.stale_stories.length > 0 ? 'text-destructive' : ''}
          />
          <WorkloadStatCard label="At Frontier" value={data.stories_at_frontier.length} />
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Counts by scope                                                      */}
      {/* ------------------------------------------------------------------ */}
      <section data-testid="scope-section">
        <SectionHeader title="Stories by Scope" />
        <div className="mt-3">
          <ScopesStrip counts={data.counts_by_scope} />
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Per-GM queue depth                                                   */}
      {/* ------------------------------------------------------------------ */}
      <section data-testid="per-gm-section">
        <SectionHeader title="Per-GM Queue Depth" count={data.per_gm_queue_depth.length} />
        <div className="mt-4">
          <PerGMQueueTable entries={data.per_gm_queue_depth} />
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Stale stories                                                        */}
      {/* ------------------------------------------------------------------ */}
      <section data-testid="stale-stories-section">
        <SectionHeader title="Stale Stories" count={data.stale_stories.length} />
        <div className="mt-4">
          <StaleStoriesTable entries={data.stale_stories} />
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Stories at frontier                                                  */}
      {/* ------------------------------------------------------------------ */}
      <section data-testid="frontier-section">
        <SectionHeader title="Stories at Frontier" count={data.stories_at_frontier.length} />
        <div className="mt-4">
          <FrontierStoriesTable entries={data.stories_at_frontier} />
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Manual actions                                                       */}
      {/* ------------------------------------------------------------------ */}
      <section data-testid="manual-actions-section">
        <SectionHeader title="Manual Actions" />
        <div className="mt-4">
          <ExpireBeatsButton />
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function StaffWorkloadPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: storiesKeys.staffWorkload(),
    queryFn: getStaffWorkload,
    throwOnError: false,
    retry: false,
  });

  let content: React.ReactNode;

  if (error) {
    const status = (error as Error & { status?: number }).status;
    if (status === 403) {
      content = <AccessDeniedPage />;
    } else {
      throw error;
    }
  } else if (isLoading) {
    content = <LoadingSkeleton />;
  } else if (data) {
    content = <StaffWorkloadInner data={data} />;
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="mb-8 text-2xl font-bold">Staff Workload</h1>
      {content}
    </div>
  );
}
