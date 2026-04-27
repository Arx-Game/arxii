/**
 * MyStoryOffersPage — GM's inbox for incoming story offers.
 *
 * Wave 5: GM offer inbox.
 *
 * Tabs:
 *   - Pending: offers in PENDING status; GM can Accept or Decline.
 *   - Decided: ACCEPTED, DECLINED, WITHDRAWN — read-only history.
 *
 * Queryset scoping: the backend's StoryGMOfferViewSet.get_queryset()
 * automatically scopes to offers directed at the requesting user's
 * gm_profile (no need to pass offered_to explicitly). Calling
 * /api/story-gm-offers/?status=pending returns only pending offers
 * sent to this GM.
 *
 * For non-GMs who hit the page: the API returns 200 with an empty list
 * (the get_queryset filter builds an empty Q() when gm_profile doesn't
 * exist), so no special 403 handling is needed.
 */

import { useState } from 'react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { OfferRow } from '../components/OfferRow';
import { useStoryGMOffers } from '../queries';

// ---------------------------------------------------------------------------
// Tab definitions
// ---------------------------------------------------------------------------

type OfferTab = 'pending' | 'decided';

const TABS: { value: OfferTab; label: string }[] = [
  { value: 'pending', label: 'Pending' },
  { value: 'decided', label: 'Decided' },
];

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function OffersSkeleton() {
  return (
    <div className="space-y-3" data-testid="offers-skeleton">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="animate-pulse rounded-lg border bg-card p-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-4 w-16" />
          </div>
          <div className="mt-2">
            <Skeleton className="h-4 w-full" />
          </div>
          <div className="mt-1">
            <Skeleton className="h-4 w-2/3" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Per-tab content
// ---------------------------------------------------------------------------

interface OffersTabContentProps {
  tab: OfferTab;
}

function OffersTabContent({ tab }: OffersTabContentProps) {
  // For the "pending" tab, filter by status=pending.
  // For the "decided" tab, we fetch all non-pending by omitting status
  // and then client-filter — or we could fetch each status separately.
  // Simplest approach: fetch status=pending for pending, no status filter
  // for decided (backend returns everything the user can see, then we
  // client-filter out pending rows).
  const isPendingTab = tab === 'pending';
  const { data, isLoading } = useStoryGMOffers(
    isPendingTab ? { status: 'pending', page_size: 50 } : { page_size: 100 }
  );

  if (isLoading) {
    return <OffersSkeleton />;
  }

  const allOffers = data?.results ?? [];
  const offers = isPendingTab
    ? allOffers.filter((o) => o.status === 'pending')
    : allOffers.filter((o) => o.status !== 'pending');

  if (offers.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground" data-testid="empty-state">
        {isPendingTab ? 'No pending offers.' : 'No decided offers yet.'}
      </p>
    );
  }

  return (
    <div className="space-y-3" data-testid="offers-list">
      {offers.map((offer) => (
        <OfferRow key={offer.id} offer={offer} showActions={isPendingTab} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function MyStoryOffersPage() {
  const [activeTab, setActiveTab] = useState<OfferTab>('pending');

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <h1 className="mb-6 text-2xl font-bold">My Story Offers</h1>

      {/* Status tabs */}
      <div
        className="mb-6 flex flex-wrap gap-1 border-b"
        role="tablist"
        aria-label="Offer status tabs"
      >
        {TABS.map((tab) => (
          <button
            key={tab.value}
            role="tab"
            aria-selected={activeTab === tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`rounded-t-md border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.value
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
          <OffersTabContent tab={activeTab} />
        </ErrorBoundary>
      </div>
    </div>
  );
}
