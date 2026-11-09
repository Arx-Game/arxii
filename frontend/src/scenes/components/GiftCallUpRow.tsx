/**
 * "Your gift" (#5018): call up a gift's substance with no technique, as a small touch of
 * play (the room dims around her). One button per gift, with what it costs here. Never
 * disabled or hidden for anima: past her anima it goes through deficit and soulfray, and
 * when she carries soulfray the server asks for one confirmation, shown here.
 */
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import { useCallUpOffers } from '../actionQueries';
import type { CallUpOffer } from '../actionTypes';

interface GiftCallUpRowProps {
  characterId: number;
  initiatorPersonaId: number | null;
}

export function GiftCallUpRow({ characterId, initiatorPersonaId }: GiftCallUpRowProps) {
  const queryClient = useQueryClient();
  const { data: offers = [] } = useCallUpOffers(initiatorPersonaId);
  const dispatch = useDispatchPlayerAction(characterId);
  const [confirming, setConfirming] = useState<{ giftId: number; message: string } | null>(null);

  if (offers.length === 0) {
    return null;
  }

  const callUp = async (offer: CallUpOffer, confirm: boolean) => {
    const result = await dispatch.mutateAsync({
      ref: { backend: 'registry', registry_key: 'call_up_substance' },
      kwargs: { gift_id: offer.gift_id, confirm_soulfray_risk: confirm },
    });
    const data = (result.data ?? {}) as { needs_soulfray_confirm?: boolean };
    if (data.needs_soulfray_confirm) {
      setConfirming({ giftId: offer.gift_id, message: result.message ?? '' });
      return;
    }
    setConfirming(null);
    if (isDispatchFailure(result)) {
      toast.error(result.message ?? 'That did not work.');
    } else if (result.message) {
      toast.success(result.message);
    }
    void queryClient.invalidateQueries({ queryKey: ['call-up-offers'] });
    void queryClient.invalidateQueries({ queryKey: ['castable-techniques'] });
  };

  return (
    <div className="space-y-1 rounded border border-muted p-2" data-testid="gift-call-up-row">
      <p className="text-xs font-semibold">Your gift</p>
      {offers.map((offer) => (
        <div key={offer.gift_id} className="space-y-1">
          <div className="flex items-center justify-between gap-2 text-xs">
            <Button
              size="sm"
              variant="secondary"
              disabled={dispatch.isPending}
              onClick={() => void callUp(offer, false)}
            >
              Call up {offer.label}
            </Button>
            <span
              className={
                offer.effective_cost === 0 && offer.resonance_cost === 0
                  ? 'text-sky-600 dark:text-sky-400'
                  : 'text-amber-700 dark:text-amber-400'
              }
            >
              {offer.cost_line}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">{offer.balance_line}</p>
          {confirming?.giftId === offer.gift_id && (
            <div className="space-y-1 rounded-md border border-amber-500/60 bg-amber-950/40 p-2 text-xs">
              <p>{confirming.message}</p>
              <Button
                size="sm"
                variant="destructive"
                disabled={dispatch.isPending}
                onClick={() => void callUp(offer, true)}
              >
                Call it up anyway
              </Button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
