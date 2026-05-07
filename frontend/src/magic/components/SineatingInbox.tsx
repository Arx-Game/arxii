/**
 * SineatingInbox — polled banner listing pending Sineating offers.
 *
 * Self-fetches via usePendingSineatingOffers() with a 5-second refetch interval.
 * The Sineater (the currently puppeted character) sees each offer and can Accept
 * or Decline. Accepting fires the full max units_offered; declining sends 0.
 *
 * Pattern: cloned from ConsentPrompt.tsx (same polling + banner structure).
 */

import { useSelector } from 'react-redux';
import { Zap, Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { RootState } from '@/store/store';
import { usePendingSineatingOffers, useRespondToSineating } from '@/magic/queries';
import type { SineatingPendingOffer } from '@/magic/types';

// ---------------------------------------------------------------------------
// Sub-component: one offer row
// ---------------------------------------------------------------------------

interface OfferRowProps {
  offer: SineatingPendingOffer;
  sineaterSheetId: number;
  isPending: boolean;
  onAccept: (offer: SineatingPendingOffer, sineaterSheetId: number) => void;
  onDecline: (offer: SineatingPendingOffer, sineaterSheetId: number) => void;
}

function OfferRow({ offer, sineaterSheetId, isPending, onAccept, onDecline }: OfferRowProps) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-violet-500/50 bg-violet-50 px-4 py-3 dark:bg-violet-950/30">
      <Zap className="h-5 w-5 shrink-0 text-violet-600" />
      <div className="flex-1">
        <p className="text-sm font-medium">
          <span className="font-semibold">{offer.sinner_persona_name}</span> offers to transfer{' '}
          <span className="font-semibold">
            {offer.units_offered} unit{offer.units_offered !== 1 ? 's' : ''}
          </span>{' '}
          of sin&nbsp;
          <span className="text-muted-foreground">
            ({offer.anima_cost_per_unit} anima / {offer.fatigue_cost_per_unit} fatigue per unit)
          </span>
          .
        </p>
      </div>
      <div className="flex items-center gap-1.5">
        <Button
          size="sm"
          variant="outline"
          onClick={() => onDecline(offer, sineaterSheetId)}
          disabled={isPending}
        >
          <X className="mr-1 h-3.5 w-3.5" />
          Decline
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => onAccept(offer, sineaterSheetId)}
          disabled={isPending}
        >
          <Check className="mr-1 h-3.5 w-3.5" />
          Accept
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function SineatingInbox() {
  const account = useSelector((state: RootState) => state.auth.account);

  const activeCharacter =
    account?.available_characters?.find((c) => c.currently_puppeted_in_session) ?? null;
  const sineaterSheetId = activeCharacter?.id ?? null;

  // Poll every 5 seconds so the Sineater sees new offers without refreshing.
  const { data } = usePendingSineatingOffers();
  const respond = useRespondToSineating();

  const offers = data?.results ?? [];

  // No puppeted character or no offers: render nothing.
  if (!sineaterSheetId || offers.length === 0) return null;

  function handleAccept(offer: SineatingPendingOffer, sheetId: number) {
    respond.mutate({
      sinner_sheet_id: offer.sinner_sheet_id,
      sineater_sheet_id: sheetId,
      units_accepted: offer.units_offered,
    });
  }

  function handleDecline(offer: SineatingPendingOffer, sheetId: number) {
    respond.mutate({
      sinner_sheet_id: offer.sinner_sheet_id,
      sineater_sheet_id: sheetId,
      units_accepted: 0,
    });
  }

  return (
    <div className="space-y-2">
      {offers.map((offer: SineatingPendingOffer) => (
        <OfferRow
          key={offer.id}
          offer={offer}
          sineaterSheetId={sineaterSheetId}
          isPending={respond.isPending}
          onAccept={handleAccept}
          onDecline={handleDecline}
        />
      ))}
    </div>
  );
}
