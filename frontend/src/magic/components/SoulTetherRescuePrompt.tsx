/**
 * SoulTetherRescuePrompt — reactive opt-in banner for stage-advance bonus offers.
 *
 * Self-fetches via usePendingStageAdvanceOffers() with a 5-second refetch interval.
 * Surfaces when the Sineater has a pending stage-advance bonus offer (the Sinner is
 * about to advance their corruption stage and the Sineater can spend Hollow units to
 * take Strain and soften the advance).
 *
 * Expired offers (expires_at < now) are filtered client-side so stale rows never
 * flash between polling cycles.
 *
 * Style: amber/red warning palette, matching SoulfrayWarning.tsx.
 * Pattern: polled banner, cloned from SineatingInbox.tsx.
 */

import { useQuery } from '@tanstack/react-query';
import { useSelector } from 'react-redux';
import { AlertTriangle, Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { RootState } from '@/store/store';
import { magicKeys, useRespondToStageAdvance } from '@/magic/queries';
import { getPendingStageAdvanceOffers } from '@/magic/api';
import type { PendingStageAdvanceOffer } from '@/magic/types';

// ---------------------------------------------------------------------------
// Sub-component: one offer row
// ---------------------------------------------------------------------------

interface OfferRowProps {
  offer: PendingStageAdvanceOffer;
  sineaterSheetId: number;
  isPending: boolean;
  onConfirm: (offer: PendingStageAdvanceOffer, sineaterSheetId: number) => void;
  onDecline: (offer: PendingStageAdvanceOffer, sineaterSheetId: number) => void;
}

function OfferRow({ offer, sineaterSheetId, isPending, onConfirm, onDecline }: OfferRowProps) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-amber-500/50 bg-amber-950/30 px-4 py-3">
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
      <div className="flex-1">
        <p className="text-sm font-semibold text-amber-200">
          <span>{offer.sinner_persona_name}</span> is about to advance to corruption{' '}
          <span>stage {offer.sinner_corruption_stage}</span>
        </p>
        <p className="mt-0.5 text-sm text-amber-300/80">
          Commit up to <span className="font-semibold">{offer.commit_units_max}</span> Hollow unit
          {offer.commit_units_max !== 1 ? 's' : ''} —{' '}
          <span className="font-semibold">{offer.strain_cost_per_unit} Strain per unit</span> — to
          soften the advance.
        </p>
      </div>
      <div className="flex items-center gap-1.5">
        <Button
          size="sm"
          variant="outline"
          onClick={() => onDecline(offer, sineaterSheetId)}
          disabled={isPending}
          className="border-amber-700 text-amber-300 hover:bg-amber-900/50"
        >
          <X className="mr-1 h-3.5 w-3.5" />
          Decline
        </Button>
        <Button
          size="sm"
          onClick={() => onConfirm(offer, sineaterSheetId)}
          disabled={isPending}
          className="bg-amber-700 text-white hover:bg-amber-600"
        >
          <Check className="mr-1 h-3.5 w-3.5" />
          Confirm
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function SoulTetherRescuePrompt() {
  const account = useSelector((state: RootState) => state.auth.account);

  const activeCharacter =
    account?.available_characters?.find((c) => c.currently_puppeted_in_session) ?? null;
  const sineaterSheetId = activeCharacter?.id ?? null;

  const { data } = useQuery({
    queryKey: magicKeys.stageAdvancePending(),
    queryFn: () => getPendingStageAdvanceOffers(),
    refetchInterval: 5_000,
  });

  const respond = useRespondToStageAdvance();

  const now = Date.now();
  const allOffers = data?.results ?? [];
  // Filter expired offers client-side so stale rows don't flash between fetches.
  const offers = allOffers.filter((o) => new Date(o.expires_at).getTime() > now);

  if (!sineaterSheetId || offers.length === 0) return null;

  function handleConfirm(offer: PendingStageAdvanceOffer, sheetId: number) {
    respond.mutate({
      sinner_sheet_id: offer.sinner_sheet_id,
      sineater_sheet_id: sheetId,
      units_committed: offer.commit_units_max,
    });
  }

  function handleDecline(offer: PendingStageAdvanceOffer, sheetId: number) {
    respond.mutate({
      sinner_sheet_id: offer.sinner_sheet_id,
      sineater_sheet_id: sheetId,
      units_committed: 0,
    });
  }

  return (
    <div className="space-y-2">
      {offers.map((offer: PendingStageAdvanceOffer) => (
        <OfferRow
          key={offer.id}
          offer={offer}
          sineaterSheetId={sineaterSheetId}
          isPending={respond.isPending}
          onConfirm={handleConfirm}
          onDecline={handleDecline}
        />
      ))}
    </div>
  );
}
