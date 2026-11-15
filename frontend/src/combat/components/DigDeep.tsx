/**
 * DigDeep - the "Dig deep" button (#4738, demo Screen 1).
 *
 * Digging deep is an immediate act (once a round, not the declared action) that rolls resolve
 * to raise her own intensity. The button says what it costs: the configured fatigue, or
 * "free" while she holds a free dig deep from an ally's encouragement. Shown only when the
 * viewer's own participant row carries a `dig_deep` offer (the server sends it to its owner).
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import type { components } from '@/generated/api';
import { isDispatchFailure, type DispatchActionRequest, type DispatchResult } from '@/combat/types';
import { digDeepChipLabel, digDeepCostLabel, digDeepRequest } from '@/combat/diggingDeep';
import type { KindledResonance } from '@/magic/types';

type DigDeepOffer = components['schemas']['DigDeepOffer'];

export interface DigDeepProps {
  offer: DigDeepOffer;
  /** The resonances she holds, which she may name to draw on (kindled ones surge more). */
  resonances?: KindledResonance[];
  isLocked: boolean;
  dispatchAction: (params: DispatchActionRequest) => Promise<DispatchResult>;
  onDispatched?: () => void;
}

export function DigDeep({
  offer,
  resonances = [],
  isLocked,
  dispatchAction,
  onDispatched,
}: DigDeepProps) {
  const [chosenId, setChosenId] = useState<number | null>(null);
  // A resonance that stops being offered (she lost it) is not sent.
  const chosen = resonances.find((row) => row.id === chosenId) ?? null;

  const digDeep = () => {
    dispatchAction(digDeepRequest(chosen?.id))
      .then((result) => {
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'You could not dig deep.');
          return;
        }
        if (result.message) toast.success(result.message);
        onDispatched?.();
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'You could not dig deep.');
      });
  };

  return (
    <section className="space-y-1.5" data-testid="dig-deep">
      {resonances.length > 0 && (
        <div className="space-y-1" data-testid="dig-deep-resonances">
          <p className="text-xs text-muted-foreground">Draw on</p>
          <div className="flex flex-wrap gap-1">
            {resonances.map((row) => {
              const on = row.id === chosen?.id;
              return (
                <button
                  key={row.id}
                  type="button"
                  disabled={isLocked || offer.dug_deep_this_round}
                  aria-pressed={on}
                  data-testid={`dig-deep-resonance-${row.id}`}
                  onClick={() => setChosenId(on ? null : row.id)}
                  className={cn(
                    'rounded-full border px-2 py-0.5 text-xs transition-colors',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                    on
                      ? 'border-primary bg-primary/10 font-medium'
                      : 'border-border hover:bg-muted/50'
                  )}
                >
                  {row.name}
                </button>
              );
            })}
          </div>
          {chosen?.kindled && (
            <p className="text-xs text-muted-foreground" data-testid="dig-deep-kindled-note">
              {chosen.name} is kindled, so the surge is larger.
            </p>
          )}
        </div>
      )}
      <button
        type="button"
        data-testid="dig-deep-button"
        disabled={isLocked || offer.dug_deep_this_round}
        onClick={digDeep}
        className={cn(
          'flex w-full items-center justify-between rounded border border-border px-3 py-1.5',
          'text-left text-sm hover:bg-muted/50',
          (isLocked || offer.dug_deep_this_round) && 'cursor-not-allowed opacity-50'
        )}
      >
        <span className="font-medium">Dig deep</span>
        <span className="text-xs text-muted-foreground" data-testid="dig-deep-cost">
          {digDeepCostLabel(offer)}
        </span>
      </button>
      {offer.free_dig_deeps > 0 && (
        <p
          className="inline-block rounded-full bg-primary/10 px-2 py-0.5 text-xs"
          data-testid="dig-deep-chip"
        >
          {digDeepChipLabel(offer)}
        </p>
      )}
    </section>
  );
}
