/**
 * OfferRow — single GM offer row for MyStoryOffersPage.
 *
 * Shows:
 *   - Story title + scope badge
 *   - Offerer account name
 *   - Relative timestamp
 *   - Message excerpt (if present)
 *   - Status badge (on Decided tab)
 *   - Accept / Decline action buttons (on Pending tab)
 */

import { formatRelativeTime } from '@/lib/relativeTime';
import { ScopeBadge } from './ScopeBadge';
import { AcceptOfferDialog } from './AcceptOfferDialog';
import { DeclineOfferDialog } from './DeclineOfferDialog';
import type { StoryGMOffer, StoryGMOfferStatus } from '../types';

// ---------------------------------------------------------------------------
// Status badge colors
// ---------------------------------------------------------------------------

const STATUS_LABELS: Record<StoryGMOfferStatus, string> = {
  pending: 'Pending',
  accepted: 'Accepted',
  declined: 'Declined',
  withdrawn: 'Withdrawn',
};

const STATUS_CLASSES: Record<StoryGMOfferStatus, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  accepted: 'bg-green-100 text-green-800',
  declined: 'bg-red-100 text-red-800',
  withdrawn: 'bg-gray-100 text-gray-600',
};

// ---------------------------------------------------------------------------
// Minimal story info fetched from the offer — the offer only returns story ID.
// The parent page pre-fetches story titles via a separate query or the
// caller passes storyTitle directly.
// ---------------------------------------------------------------------------

interface OfferRowProps {
  offer: StoryGMOffer;
  storyTitle?: string;
  storyScope?: string;
  /** When true, show Accept/Decline action buttons (Pending tab only). */
  showActions?: boolean;
}

export function OfferRow({ offer, storyTitle, storyScope, showActions = false }: OfferRowProps) {
  return (
    <div className="rounded-lg border bg-card p-4" data-testid="offer-row" data-offer-id={offer.id}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        {/* Left: story info + offerer */}
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium" data-testid="offer-story-title">
              {storyTitle ?? `Story #${offer.story}`}
            </span>
            {storyScope && (
              <ScopeBadge scope={storyScope as Parameters<typeof ScopeBadge>[0]['scope']} />
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            From account #{offer.offered_by_account} •{' '}
            <span title={offer.created_at}>{formatRelativeTime(offer.created_at)}</span>
          </p>
          {offer.message && (
            <p
              className="mt-1 line-clamp-2 text-sm text-muted-foreground"
              data-testid="offer-message-excerpt"
            >
              &quot;{offer.message}&quot;
            </p>
          )}
        </div>

        {/* Right: status badge or action buttons */}
        <div className="flex items-center gap-2">
          {!showActions && (
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[offer.status]}`}
              data-testid="offer-status-badge"
            >
              {STATUS_LABELS[offer.status]}
            </span>
          )}
          {showActions && offer.status === 'pending' && (
            <>
              <AcceptOfferDialog offer={offer} storyTitle={storyTitle} />
              <DeclineOfferDialog offer={offer} storyTitle={storyTitle} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
