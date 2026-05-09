/**
 * WeavingTeachingOffersPage — browse all ThreadWeavingTeachingOffer records.
 *
 * Route: /threads/teaching
 *
 * Layout:
 *   Header "Thread Weaving Teaching Offers"
 *   List of TeachingOfferCards (one per offer)
 *   Loading skeleton while fetching
 *   Empty state when no offers are available
 *
 * Null effective_xp_cost_for_viewer (alt-ambiguous) disables the Accept button
 * and shows "Select character to see XP cost" inline in TeachingOfferCard.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Skeleton } from '@/components/ui/skeleton';
import { useTeachingOffers } from '../queries';
import { TeachingOfferCard } from '../components/threads/TeachingOfferCard';
import { AcceptOfferDialog } from '../components/threads/AcceptOfferDialog';
import type { ThreadWeavingTeachingOffer } from '../types';

export function WeavingTeachingOffersPage() {
  const { data, isLoading } = useTeachingOffers();
  const [selectedOffer, setSelectedOffer] = useState<ThreadWeavingTeachingOffer | null>(null);

  const offers = data?.results ?? [];

  const handleAccept = (offer: ThreadWeavingTeachingOffer) => {
    setSelectedOffer(offer);
  };

  const handleDialogClose = (open: boolean) => {
    if (!open) {
      setSelectedOffer(null);
    }
  };

  return (
    <div className="container mx-auto space-y-6 px-4 py-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Thread Weaving Teaching Offers</h1>
        <Link
          to="/threads"
          className="text-sm text-muted-foreground underline hover:text-foreground"
        >
          Back to Threads
        </Link>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="space-y-3" data-testid="teaching-offers-loading">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28 w-full rounded-lg" />
          ))}
        </div>
      ) : offers.length === 0 ? (
        <div
          className="rounded-lg border border-dashed px-6 py-12 text-center"
          data-testid="teaching-offers-empty"
        >
          <p className="text-muted-foreground">No teaching offers available right now.</p>
        </div>
      ) : (
        <div className="space-y-3" data-testid="teaching-offers-list">
          {offers.map((offer) => (
            <TeachingOfferCard key={offer.id} offer={offer} onAccept={handleAccept} />
          ))}
        </div>
      )}

      {/* Accept Offer dialog */}
      {selectedOffer && (
        <AcceptOfferDialog
          offer={selectedOffer}
          open={selectedOffer !== null}
          onOpenChange={handleDialogClose}
        />
      )}
    </div>
  );
}
