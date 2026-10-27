/**
 * DriftConversionOfferDialog (#4733, Screen 5 of the approved demo) - the
 * conversion offer a deed in a live scene opens.
 *
 * One framed box, as drawn: the small-caps label "Conversion offer · this scene",
 * a line of system text naming the drift held and the resonance it can become,
 * the component pills (the chosen one filled in the primary colour), the rate line,
 * and one right-aligned row holding Decline and Perform the rite. Additions beyond
 * the drawing sit quietly inside the same box: the cap remaining, a source picker
 * when there is more than one source (one source is a plain chip), and the amount.
 * With more than one cap each cap gets its own section; Decline sits in the last
 * section's row, since it lets the whole offer go.
 */

import { useState, type ReactNode } from 'react';
import { Flame } from 'lucide-react';
import { Dialog, DialogContent, DialogTitle, NO_DESCRIPTION } from '@/components/ui/dialog';
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

const ERROR_CLASS =
  'rounded-md border border-red-600/60 bg-red-50 p-3 text-sm font-medium text-red-800 dark:bg-red-950/40 dark:text-red-200';

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

/** "A", "A and B", "A, B and C". */
function joinNames(names: string[]): string {
  if (names.length <= 1) return names.join('');
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

/** The system line: the drift she holds toward this cap, and what it can become. */
function driftSystemLine(cap: DriftConversionCap): string | null {
  const held = cap.sources.filter((s) => s.balance > 0).map((s) => s.resonance_name);
  if (held.length === 0) return null;
  return `You hold ${joinNames(held)} that does not fit you. Convert it to ${cap.target_resonance.name}.`;
}

/** Unselected pills are outlined; the chosen one is filled in the theme's primary pair. */
function pillClass(selected: boolean): string {
  return `rounded-full border px-3 py-1 text-sm transition-colors ${
    selected
      ? 'border-primary bg-primary font-semibold text-primary-foreground'
      : 'border-input bg-transparent text-foreground hover:bg-accent hover:text-accent-foreground'
  }`;
}

const CHIP_CLASS = 'rounded-full border border-input px-3 py-1 text-sm text-muted-foreground';

function sourceLabel(s: DriftSourceOption): string {
  return `${s.resonance_name} · ${s.balance} held · ${conversionLabel(s.conversion_type)} · up to ${s.projected_output}`;
}

function resultText(
  result: DriftCorrectionResult,
  source: DriftSourceOption | undefined,
  target: string
): string {
  // Same words as the telnet verb for a failed roll.
  if (result.converted_amount === 0) return 'The rite fails; nothing is converted.';
  const sourceName = source?.resonance_name ?? 'drift';
  return `${result.outcome_name}: ${result.converted_amount} ${sourceName} became ${result.granted_amount} ${target}.`;
}

interface CapBlockProps {
  offerId: number;
  cap: DriftConversionCap;
  /** Null while the rite is ready; else the server's sentence saying it is not set up. */
  notReadyMessage: string | null;
  onResult: (line: string) => void;
  /** Rendered before Perform the rite in this block's button row (the offer's Decline). */
  rowStart?: ReactNode;
}

function CapBlock({ offerId, cap, notReadyMessage, onResult, rowStart }: CapBlockProps) {
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
  const canPerform =
    notReadyMessage === null && source !== undefined && componentId !== null && amountValid;
  const systemLine = driftSystemLine(cap);

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
    <section className="space-y-3 py-3 first:pt-0 last:pb-0" data-testid={`drift-cap-${targetId}`}>
      <div className="flex items-baseline justify-between gap-2">
        {systemLine ? (
          <p className="text-sm" data-testid={`drift-system-line-${targetId}`}>
            {systemLine}
          </p>
        ) : (
          <span />
        )}
        <span className="shrink-0 text-xs text-muted-foreground">
          Cap remaining{' '}
          <span
            className="font-semibold text-foreground"
            data-testid={`drift-cap-remaining-${targetId}`}
          >
            {cap.cap_remaining}
          </span>
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {cap.sources.length > 1 ? (
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
                {sourceLabel(s)}
              </button>
            ))}
          </div>
        ) : null}
        {cap.sources.length === 1 && source ? (
          <span
            className={CHIP_CLASS}
            data-testid={`drift-source-${targetId}-${source.resonance_id}`}
          >
            {sourceLabel(source)}
          </span>
        ) : null}
        {source ? (
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            Amount
            <Input
              type="number"
              inputMode="numeric"
              min={1}
              max={maxAmount}
              value={amountText ?? String(maxAmount)}
              onChange={(e) => changeAmount(e.target.value)}
              aria-invalid={!amountValid}
              className="h-8 w-20"
              data-testid={`drift-amount-${targetId}`}
            />
          </label>
        ) : null}
      </div>

      {notReadyMessage !== null ? (
        <p className="text-sm text-muted-foreground" data-testid={`drift-not-ready-${targetId}`}>
          {notReadyMessage}
        </p>
      ) : (
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
      )}

      {source && amountValid ? (
        <p className="text-sm" data-testid={`drift-rate-${targetId}`}>
          {conversionLabel(source.conversion_type)}: {amount} {source.resonance_name} becomes about{' '}
          {projectedOutput(amount, source.multiplier)} {cap.target_resonance.name}
          {focusClause}
        </p>
      ) : null}

      {convert.isError ? (
        <div role="alert" data-testid="drift-error" className={ERROR_CLASS}>
          {convert.error?.message || 'The rite did not take; please try again.'}
        </div>
      ) : null}

      <div className="flex justify-end gap-2" data-testid={`drift-actions-${targetId}`}>
        {rowStart}
        <Button
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

  const caps = offer?.caps ?? [];
  const declineButton = (
    <Button variant="outline" onClick={handleDecline} disabled={decline.isPending}>
      Decline
    </Button>
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent {...NO_DESCRIPTION} className="max-h-[90vh] space-y-1 overflow-y-auto">
        <DialogTitle className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Conversion offer · this scene
        </DialogTitle>

        {resultLine ? (
          <p className="text-sm" role="status" data-testid="drift-result">
            {resultLine}
          </p>
        ) : null}

        <div className="divide-y divide-border">
          {offer
            ? caps.map((cap, index) => (
                <CapBlock
                  key={`${offer.id}-${cap.target_resonance.id}`}
                  offerId={offer.id}
                  cap={cap}
                  notReadyMessage={offer.rite_ready ? null : offer.rite_not_ready_message}
                  onResult={onResult}
                  rowStart={index === caps.length - 1 ? declineButton : undefined}
                />
              ))
            : null}
        </div>

        {decline.isError ? (
          <div role="alert" data-testid="drift-decline-error" className={ERROR_CLASS}>
            {decline.error?.message || 'The offer could not be declined; please try again.'}
          </div>
        ) : null}

        {!offer || caps.length === 0 ? (
          <div className="flex justify-end gap-2">
            {offer ? (
              declineButton
            ) : (
              <Button variant="outline" onClick={onClose}>
                Close
              </Button>
            )}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
