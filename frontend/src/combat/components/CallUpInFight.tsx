/**
 * Calling up her gift's substance in a fight (#5018): a button beside Dig deep. An
 * immediate act, once a round, never the round's declared action. The button says what
 * it costs; it is never disabled for anima (past her anima it goes through deficit and
 * soulfray), only once this round's call-up is spent or the round is not open.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import type { components } from '@/generated/api';
import { isDispatchFailure, type DispatchActionRequest, type DispatchResult } from '@/combat/types';

type CallUpFightOffer = components['schemas']['CallUpFightOffer'];
type CallUpOffer = components['schemas']['CallUpOffer'];

export interface CallUpInFightProps {
  offer: CallUpFightOffer;
  isLocked: boolean;
  dispatchAction: (params: DispatchActionRequest) => Promise<DispatchResult>;
  onDispatched?: () => void;
}

export function CallUpInFight({
  offer,
  isLocked,
  dispatchAction,
  onDispatched,
}: CallUpInFightProps) {
  const [confirm, setConfirm] = useState<{ giftId: number; message: string } | null>(null);
  const spent = offer.called_up_this_round;

  const callUp = (gift: CallUpOffer, confirmed: boolean) => {
    dispatchAction({
      ref: { backend: 'registry', registry_key: 'call_up_substance' },
      kwargs: { gift_id: gift.gift_id, confirm_soulfray_risk: confirmed },
    })
      .then((result) => {
        const data = (result.data ?? {}) as { needs_soulfray_confirm?: boolean };
        if (data.needs_soulfray_confirm) {
          setConfirm({ giftId: gift.gift_id, message: result.message ?? '' });
          return;
        }
        setConfirm(null);
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'You could not call it up.');
          return;
        }
        if (result.message) toast.success(result.message);
        onDispatched?.();
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'You could not call it up.');
      });
  };

  return (
    <section className="space-y-1.5" data-testid="call-up-in-fight">
      {offer.offers.map((gift) => (
        <div key={gift.gift_id} className="space-y-1">
          <button
            type="button"
            data-testid="call-up-button"
            disabled={isLocked || spent}
            onClick={() => callUp(gift, false)}
            className={cn(
              'flex w-full items-center justify-between rounded border border-border px-3 py-1.5',
              'text-left text-sm hover:bg-muted/50',
              (isLocked || spent) && 'cursor-not-allowed opacity-50'
            )}
          >
            <span className="font-medium">Call up {gift.label}</span>
            <span className="text-xs text-muted-foreground" data-testid="call-up-cost">
              {gift.cost_line}
            </span>
          </button>
          {confirm?.giftId === gift.gift_id && (
            <div className="space-y-1 rounded-md border border-amber-500/60 bg-amber-950/40 p-2 text-xs">
              <p>{confirm.message}</p>
              <button
                type="button"
                className="rounded border border-amber-500/60 px-2 py-0.5"
                onClick={() => callUp(gift, true)}
              >
                Call it up anyway
              </button>
            </div>
          )}
        </div>
      ))}
      <p className="text-xs text-muted-foreground">Once a round. Not your action for the round.</p>
    </section>
  );
}
