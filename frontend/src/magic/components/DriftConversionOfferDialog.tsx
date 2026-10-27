/**
 * DriftConversionOfferDialog (#4733, Screen 5 of the approved demo) - the
 * conversion offer a deed in a live scene opens.
 *
 * One block per target resonance the offer holds a cap for: the cap remaining, a
 * source picker (the drifts the rite could convert toward that target), an amount
 * bounded by the chosen source's max_amount, a single-select component pill group
 * and a rate line built from the server's preview. Chip style mirrors
 * EntryFlourishOfferDialog.
 */

import { useState } from 'react';
import { Flame } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  NO_DESCRIPTION,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useConvertDrift, useDeclineDriftConversion } from '@/magic/queries';
import type {
  DriftConversionCap,
  DriftConversionOffer,
  DriftCorrectionResult,
  DriftSourceOption,
} from '@/magic/types';

const CONVERSION_TYPE_LABELS: Record<string, string> = {
  FALL: 'Fall',
  REDEMPTION: 'Redemption',
};

function conversionLabel(conversionType: string): string {
  return CONVERSION_TYPE_LABELS[conversionType] ?? conversionType;
}

/** The pair-rate output of converting `amount`, floored at 1 like the server's conversion. */
function projectedOutput(amount: number, multiplier: string): number {
  if (amount <= 0) return 0;
  // The multiplier carries two decimals; whole hundredths keep the floor exact.
  const hundredths = Math.round(Number(multiplier) * 100);
  return Math.max(1, Math.floor((amount * hundredths) / 100));
}

function pillClass(selected: boolean): string {
  return `rounded-full border px-3 py-1 text-sm transition-colors ${
    selected
      ? 'border-amber-500 bg-amber-500/20 font-semibold text-amber-300'
      : 'border-muted-foreground/30 text-muted-foreground hover:border-amber-500/60 hover:text-amber-300'
  }`;
}

function resultText(
  result: DriftCorrectionResult,
  source: DriftSourceOption | undefined,
  target: string
): string {
  const sourceName = source?.resonance_name ?? 'drift';
  return `${result.outcome_name}: ${result.converted_amount} ${sourceName} became ${result.granted_amount} ${target}.`;
}

interface CapBlockProps {
  offerId: number;
  cap: DriftConversionCap;
  onResult: (line: string) => void;
}

function CapBlock({ offerId, cap, onResult }: CapBlockProps) {
  const targetId = cap.target_resonance.id;
  const [sourceId, setSourceId] = useState<number | null>(cap.sources[0]?.resonance_id ?? null);
  // null = "the source's max"; typed text is kept as typed so a half-edited amount is not snapped.
  const [amountText, setAmountText] = useState<string | null>(null);
  const [componentId, setComponentId] = useState<number | null>(null);
  const convert = useConvertDrift();

  const source = cap.sources.find((s) => s.resonance_id === sourceId) ?? cap.sources[0];
  const maxAmount = source?.max_amount ?? 0;
  const amount = amountText === null ? maxAmount : Number(amountText);
  const amountValid = Number.isInteger(amount) && amount >= 1 && amount <= maxAmount;
  const canPerform = source !== undefined && componentId !== null && amountValid;

  function pickSource(next: number) {
    convert.reset();
    setSourceId(next);
    setAmountText(null);
  }

  function pickComponent(next: number) {
    convert.reset();
    setComponentId(next);
  }

  function changeAmount(next: string) {
    convert.reset();
    setAmountText(next);
  }

  function handlePerform() {
    if (!source || componentId === null || !amountValid) return;
    convert.mutate(
      {
        offer_id: offerId,
        source_resonance_id: source.resonance_id,
        target_resonance_id: targetId,
        amount,
        component_ids: [componentId],
      },
      {
        onSuccess: (result) => {
          setComponentId(null);
          setAmountText(null);
          onResult(resultText(result, source, cap.target_resonance.name));
        },
      }
    );
  }

  const focusClause = cap.focus_bonus > 0 ? `; a focus adds ${cap.focus_bonus}` : '';

  return (
    <section
      className="space-y-3 rounded-md border border-amber-500/30 bg-amber-950/20 p-3"
      data-testid={`drift-cap-${targetId}`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-lg font-semibold text-amber-300">{cap.target_resonance.name}</h3>
        <span className="text-sm text-muted-foreground">
          Cap remaining{' '}
          <span
            className="font-semibold text-foreground"
            data-testid={`drift-cap-remaining-${targetId}`}
          >
            {cap.cap_remaining}
          </span>
        </span>
      </div>

      <div
        className="flex flex-wrap gap-2"
        role="group"
        aria-label={`Source for ${cap.target_resonance.name}`}
      >
        {cap.sources.map((s) => (
          <button
            key={s.resonance_id}
            type="button"
            aria-pressed={s.resonance_id === source?.resonance_id}
            onClick={() => pickSource(s.resonance_id)}
            data-testid={`drift-source-${targetId}-${s.resonance_id}`}
            className={pillClass(s.resonance_id === source?.resonance_id)}
          >
            {s.resonance_name} · {s.balance} held · {conversionLabel(s.conversion_type)} · up to{' '}
            {s.projected_output}
          </button>
        ))}
      </div>

      {source ? (
        <label className="flex items-center gap-2 text-sm">
          Amount
          <Input
            type="number"
            inputMode="numeric"
            min={1}
            max={maxAmount}
            value={amountText ?? String(maxAmount)}
            onChange={(e) => changeAmount(e.target.value)}
            aria-invalid={!amountValid}
            className="w-24"
            data-testid={`drift-amount-${targetId}`}
          />
        </label>
      ) : null}

      <div
        className="flex flex-wrap gap-2"
        role="group"
        aria-label={`Components for ${cap.target_resonance.name}`}
      >
        {cap.qualifying_components.map((c) => (
          <button
            key={c.item_id}
            type="button"
            aria-pressed={componentId === c.item_id}
            onClick={() => pickComponent(c.item_id)}
            data-testid={`drift-component-${c.item_id}`}
            className={pillClass(componentId === c.item_id)}
          >
            {c.name} · {c.mode}
          </button>
        ))}
      </div>

      {source && amountValid ? (
        <p className="text-sm" data-testid={`drift-rate-${targetId}`}>
          {conversionLabel(source.conversion_type)}: {amount} {source.resonance_name} becomes about{' '}
          {projectedOutput(amount, source.multiplier)} {cap.target_resonance.name}
          {focusClause}
        </p>
      ) : null}

      {convert.isError ? (
        <div
          role="alert"
          data-testid="drift-error"
          className="rounded-md border border-red-600/60 bg-red-950/40 p-3 text-sm font-medium text-red-200"
        >
          {convert.error?.message || 'The rite did not take; please try again.'}
        </div>
      ) : null}

      <div className="flex justify-end">
        <Button
          className="bg-amber-600 text-white hover:bg-amber-500"
          onClick={handlePerform}
          disabled={!canPerform || convert.isPending}
          data-testid={`drift-perform-${targetId}`}
        >
          <Flame className="mr-1.5 h-4 w-4" />
          Perform the rite
        </Button>
      </div>
    </section>
  );
}

interface DriftConversionOfferDialogProps {
  /** Null once the rite has exhausted the offer; the result line is all that is left to show. */
  offer: DriftConversionOffer | null;
  resultLine: string | null;
  onResult: (line: string) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onClose: () => void;
}

export function DriftConversionOfferDialog({
  offer,
  resultLine,
  onResult,
  open,
  onOpenChange,
  onClose,
}: DriftConversionOfferDialogProps) {
  const decline = useDeclineDriftConversion();

  function handleDecline() {
    if (!offer) return;
    decline.mutate({ offer_id: offer.id }, { onSuccess: onClose });
  }

  function handleOpenChange(next: boolean) {
    if (!next) decline.reset();
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        {...NO_DESCRIPTION}
        className="max-h-[90vh] overflow-y-auto border-amber-500/60 shadow-[0_0_60px_-12px] shadow-amber-500/50"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-2xl font-bold tracking-wide text-amber-400">
            <Flame className="h-7 w-7" />
            Conversion offer
          </DialogTitle>
        </DialogHeader>

        {resultLine ? (
          <p className="text-sm" role="status" data-testid="drift-result">
            {resultLine}
          </p>
        ) : null}

        {offer?.caps.map((cap) => (
          <CapBlock
            key={`${offer.id}-${cap.target_resonance.id}`}
            offerId={offer.id}
            cap={cap}
            onResult={onResult}
          />
        ))}

        {decline.isError ? (
          <div
            role="alert"
            data-testid="drift-decline-error"
            className="rounded-md border border-red-600/60 bg-red-950/40 p-3 text-sm font-medium text-red-200"
          >
            {decline.error?.message || 'The offer could not be declined; please try again.'}
          </div>
        ) : null}

        <DialogFooter>
          {offer ? (
            <Button variant="outline" onClick={handleDecline} disabled={decline.isPending}>
              Decline
            </Button>
          ) : (
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
