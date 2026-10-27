/**
 * SteelYourself - the "Steel yourself" button (#4738, demo Screen 1).
 *
 * Steeling is an immediate act (once a round, not the declared action) that rolls resolve
 * to raise her own intensity. The button says what it costs: the configured fatigue, or
 * "free" while she holds a free steel from an ally's encouragement. Shown only when the
 * viewer's own participant row carries a `steel` offer (the server sends it to its owner).
 */

import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import type { components } from '@/generated/api';
import { isDispatchFailure, type DispatchActionRequest, type DispatchResult } from '@/combat/types';
import { steelChipLabel, steelCostLabel, steelRequest } from '@/combat/steeling';

type SteelOffer = components['schemas']['SteelOffer'];

export interface SteelYourselfProps {
  offer: SteelOffer;
  isLocked: boolean;
  dispatchAction: (params: DispatchActionRequest) => Promise<DispatchResult>;
  onDispatched?: () => void;
}

export function SteelYourself({
  offer,
  isLocked,
  dispatchAction,
  onDispatched,
}: SteelYourselfProps) {
  const steel = () => {
    dispatchAction(steelRequest())
      .then((result) => {
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'You could not steel yourself.');
          return;
        }
        if (result.message) toast.success(result.message);
        onDispatched?.();
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'You could not steel yourself.');
      });
  };

  return (
    <section className="space-y-1.5" data-testid="steel-yourself">
      <button
        type="button"
        data-testid="steel-button"
        disabled={isLocked || offer.steeled_this_round}
        onClick={steel}
        className={cn(
          'flex w-full items-center justify-between rounded border border-border px-3 py-1.5',
          'text-left text-sm hover:bg-muted/50',
          (isLocked || offer.steeled_this_round) && 'cursor-not-allowed opacity-50'
        )}
      >
        <span className="font-medium">Steel yourself</span>
        <span className="text-xs text-muted-foreground" data-testid="steel-cost">
          {steelCostLabel(offer)}
        </span>
      </button>
      {offer.free_steels > 0 && (
        <p
          className="inline-block rounded-full bg-primary/10 px-2 py-0.5 text-xs"
          data-testid="steel-chip"
        >
          {steelChipLabel(offer)}
        </p>
      )}
    </section>
  );
}
