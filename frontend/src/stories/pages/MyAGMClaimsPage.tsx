/**
 * MyAGMClaimsPage — view and manage the current user's own AGM claims.
 *
 * Wave 7: AGM perspective.
 *
 * Status tabs: REQUESTED / APPROVED / REJECTED / COMPLETED / CANCELLED
 *
 * Filtering approach: the backend's AssistantGMClaimViewSet.get_queryset()
 * already scopes the list to the current user's own claims (via the
 * assistant_gm FK) plus claims on stories they Lead-GM. That means calling
 * /api/assistant-gm-claims/?status=<s> returns claims the user has submitted,
 * making an explicit "mine=true" param unnecessary.
 *
 * Permission gating: same graceful-403 pattern as GMQueuePage — if the user
 * has no GMProfile the API returns 403, and we render a friendly message.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { listAssistantGMClaims } from '../api';
import { storiesKeys } from '../queries';
import { MyClaimRow } from '../components/MyClaimRow';
import type { AssistantClaimStatus } from '../types';

// ---------------------------------------------------------------------------
// Status tabs
// ---------------------------------------------------------------------------

const STATUS_TABS: { value: AssistantClaimStatus; label: string }[] = [
  { value: 'requested', label: 'Requested' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'completed', label: 'Completed' },
  { value: 'cancelled', label: 'Cancelled' },
];

const EMPTY_COPY: Record<AssistantClaimStatus, string> = {
  requested: 'No pending claim requests.',
  approved: 'No approved claims right now.',
  rejected: 'No rejected claims.',
  completed: 'No completed claims yet.',
  cancelled: 'No cancelled claims.',
};

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function ClaimsSkeleton() {
  return (
    <div className="space-y-3" data-testid="claims-skeleton">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="animate-pulse rounded-lg border bg-card p-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-5 w-20" />
            <Skeleton className="h-4 w-32" />
          </div>
          <div className="mt-2">
            <Skeleton className="h-4 w-full" />
          </div>
          <div className="mt-1">
            <Skeleton className="h-4 w-3/4" />
          </div>
        </div>
      ))}
    </div>
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
// Per-status tab content
// ---------------------------------------------------------------------------

function ClaimsTabContent({ status }: { status: AssistantClaimStatus }) {
  const { data, isLoading, error } = useQuery({
    queryKey: storiesKeys.agmClaims({ status, page_size: 50 }),
    queryFn: () => listAssistantGMClaims({ status, page_size: 50 }),
    throwOnError: false,
    retry: false,
  });

  if (error) {
    const httpStatus = (error as Error & { status?: number }).status;
    if (httpStatus === 403) {
      return <NotGMPage />;
    }
    throw error;
  }

  if (isLoading) {
    return <ClaimsSkeleton />;
  }

  const claims = data?.results ?? [];

  if (claims.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground" data-testid="empty-state">
        {EMPTY_COPY[status]}
      </p>
    );
  }

  return (
    <div className="space-y-3" data-testid="claims-list">
      {claims.map((claim) => (
        <MyClaimRow key={claim.id} claim={claim} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function MyAGMClaimsPage() {
  const [activeStatus, setActiveStatus] = useState<AssistantClaimStatus>('requested');

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <h1 className="mb-6 text-2xl font-bold">My AGM Claims</h1>

      {/* Status tabs */}
      <div
        className="mb-6 flex flex-wrap gap-1 border-b"
        role="tablist"
        aria-label="Claim status tabs"
      >
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            role="tab"
            aria-selected={activeStatus === tab.value}
            onClick={() => setActiveStatus(tab.value)}
            className={`rounded-t-md border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              activeStatus === tab.value
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
            data-testid={`tab-${tab.value}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab panel */}
      <div role="tabpanel" data-testid="tab-panel">
        <ErrorBoundary>
          <ClaimsTabContent status={activeStatus} />
        </ErrorBoundary>
      </div>
    </div>
  );
}
