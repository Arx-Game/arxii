/**
 * AGMOpportunitiesPage — browse AGM-eligible beats and request claims.
 *
 * Wave 7: AGM-perspective view.
 *
 * Lists all beats with agm_eligible=true (backend filter added in Wave 7).
 * Cross-references the user's existing claims so each card can show whether
 * the current user has already claimed a given beat.
 *
 * Permission gating: only GMs have beats surface via IsBeatStoryOwnerOrStaff,
 * but the RequestClaimDialog will 403 for non-GMs — same graceful-403 pattern
 * used by GMQueuePage.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { listBeats, listAssistantGMClaims } from '../api';
import { storiesKeys } from '../queries';
import { AGMOpportunityCard } from '../components/AGMOpportunityCard';
import type { AssistantGMClaim, Beat } from '../types';

// ---------------------------------------------------------------------------
// Filter chip types
// ---------------------------------------------------------------------------

type AvailabilityFilter = 'available' | 'all';

const FILTER_CHIPS: { value: AvailabilityFilter; label: string }[] = [
  { value: 'available', label: 'Available' },
  { value: 'all', label: 'All Open' },
];

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function OpportunitiesSkeleton() {
  return (
    <div className="space-y-3" data-testid="opportunities-skeleton">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="animate-pulse rounded-lg border bg-card p-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-5 w-20" />
          </div>
          <div className="mt-2">
            <Skeleton className="h-4 w-full" />
          </div>
          <div className="mt-2">
            <Skeleton className="h-4 w-3/4" />
          </div>
          <div className="mt-3">
            <Skeleton className="h-8 w-28" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inner page component (data fetched here)
// ---------------------------------------------------------------------------

const ACTIVE_STATUSES = new Set(['requested', 'approved']);

function AGMOpportunitiesInner() {
  const [availFilter, setAvailFilter] = useState<AvailabilityFilter>('available');

  // Fetch all agm_eligible beats (page_size=100 — reasonable upper bound for
  // a GM-facing admin view; pagination can be added if the set grows large).
  const beatsQuery = useQuery({
    queryKey: storiesKeys.beatList({ agm_eligible: true, page_size: 100 }),
    queryFn: () => listBeats({ agm_eligible: true, page_size: 100 }),
    throwOnError: false,
    retry: false,
  });

  // Fetch user's own claims to cross-reference and show "already claimed" state.
  // The backend's get_queryset scopes this automatically to the current user's
  // own claims, so no assistant_gm param needed.
  const claimsQuery = useQuery({
    queryKey: storiesKeys.agmClaims({ page_size: 200 }),
    queryFn: () => listAssistantGMClaims({ page_size: 200 }),
    throwOnError: false,
    retry: false,
  });

  // 403 on beats → not a GM (IsBeatStoryOwnerOrStaff requires story access)
  if (beatsQuery.error) {
    const status = (beatsQuery.error as Error & { status?: number }).status;
    if (status === 403) {
      return (
        <div className="flex min-h-64 flex-col items-center justify-center text-center">
          <h2 className="text-xl font-semibold">Access Denied</h2>
          <p className="mt-2 max-w-md text-muted-foreground">
            You don&apos;t have a GM profile. Contact staff if you should have GM access.
          </p>
        </div>
      );
    }
    throw beatsQuery.error;
  }

  if (beatsQuery.isLoading) {
    return <OpportunitiesSkeleton />;
  }

  const beats: Beat[] = beatsQuery.data?.results ?? [];
  const myClaims: AssistantGMClaim[] = claimsQuery.data?.results ?? [];

  // Build a map: beatId → user's claims on that beat
  const claimsByBeat = new Map<number, AssistantGMClaim[]>();
  for (const claim of myClaims) {
    const beatId = claim.beat;
    if (!claimsByBeat.has(beatId)) {
      claimsByBeat.set(beatId, []);
    }
    claimsByBeat.get(beatId)!.push(claim);
  }

  // Filter beats by availability
  const filteredBeats =
    availFilter === 'available'
      ? beats.filter((b) => {
          const claimsOnBeat = claimsByBeat.get(b.id) ?? [];
          return !claimsOnBeat.some((c) => ACTIVE_STATUSES.has(c.status ?? ''));
        })
      : beats;

  return (
    <div>
      {/* Filter chips */}
      <div className="mb-4 flex flex-wrap gap-2">
        {FILTER_CHIPS.map((chip) => (
          <button
            key={chip.value}
            onClick={() => setAvailFilter(chip.value)}
            className={`rounded-full border px-3 py-1 text-sm font-medium transition-colors ${
              availFilter === chip.value
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border bg-background hover:bg-accent'
            }`}
          >
            {chip.label}
          </button>
        ))}
        <span className="ml-2 flex items-center text-sm text-muted-foreground">
          ({filteredBeats.length} beat{filteredBeats.length !== 1 ? 's' : ''})
        </span>
      </div>

      {/* Beat list */}
      <div className="space-y-3" data-testid="opportunities-list">
        {filteredBeats.length === 0 ? (
          <p className="py-8 text-center text-muted-foreground" data-testid="empty-state">
            {availFilter === 'available'
              ? 'No unclaimed beats available right now.'
              : 'No AGM-eligible beats found.'}
          </p>
        ) : (
          filteredBeats.map((beat) => (
            <AGMOpportunityCard
              key={beat.id}
              beat={beat}
              myClaimsOnBeat={claimsByBeat.get(beat.id) ?? []}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function AGMOpportunitiesPage() {
  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="mb-8 text-2xl font-bold">AGM Opportunities</h1>
      <ErrorBoundary>
        <AGMOpportunitiesInner />
      </ErrorBoundary>
    </div>
  );
}
