/**
 * TeachingOfferCard — displays a single ThreadWeavingTeachingOffer.
 *
 * Shows:
 *  - Teacher (RosterTenure PK — displayed as "Teacher #N" for v1 since the
 *    serializer does not embed a display name field)
 *  - Unlock description (unlock_target_kind + unlock_display_name)
 *  - Pitch text
 *  - XP cost (effective_xp_cost_for_viewer, already Path-multiplied)
 *  - Gold cost
 *  - [Accept Offer] button — disabled when effective_xp_cost_for_viewer is null
 */
import { Button } from '@/components/ui/button';
import type { ThreadWeavingTeachingOffer } from '../../types';

interface TeachingOfferCardProps {
  offer: ThreadWeavingTeachingOffer;
  onAccept: (offer: ThreadWeavingTeachingOffer) => void;
}

export function TeachingOfferCard({ offer, onAccept }: TeachingOfferCardProps) {
  const xpCost = offer.effective_xp_cost_for_viewer;
  const isAmbiguous = xpCost === null;

  return (
    <div
      className="rounded-lg border bg-card p-4 shadow-sm"
      data-testid={`teaching-offer-card-${offer.id}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        {/* Left column: metadata */}
        <div className="min-w-0 flex-1 space-y-1">
          {/* Teacher */}
          <p className="text-sm font-medium text-foreground" data-testid="teaching-offer-teacher">
            Teacher #{offer.teacher}
          </p>

          {/* Unlock description */}
          <p className="text-sm text-muted-foreground" data-testid="teaching-offer-unlock">
            Unlock: {offer.unlock_target_kind} &mdash; {offer.unlock_display_name}
          </p>

          {/* Pitch */}
          {offer.pitch && (
            <p className="text-sm italic text-muted-foreground" data-testid="teaching-offer-pitch">
              &ldquo;{offer.pitch}&rdquo;
            </p>
          )}

          {/* Costs */}
          <div className="flex flex-wrap gap-4 pt-1">
            <span className="text-sm" data-testid="teaching-offer-xp-cost">
              {isAmbiguous ? (
                <span className="text-muted-foreground">Select character to see XP cost</span>
              ) : (
                <>
                  <span className="font-semibold">{xpCost} XP</span>
                </>
              )}
            </span>
            {offer.gold_cost > 0 && (
              <span className="text-sm" data-testid="teaching-offer-gold-cost">
                <span className="font-semibold">{offer.gold_cost}</span>{' '}
                <span className="text-muted-foreground">Gold</span>
              </span>
            )}
          </div>
        </div>

        {/* Right column: action */}
        <div className="shrink-0">
          <Button
            type="button"
            variant="default"
            size="sm"
            disabled={isAmbiguous}
            onClick={() => onAccept(offer)}
            data-testid={`teaching-offer-accept-btn-${offer.id}`}
          >
            Accept Offer
          </Button>
        </div>
      </div>
    </div>
  );
}
