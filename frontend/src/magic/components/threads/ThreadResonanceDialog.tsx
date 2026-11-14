/**
 * ThreadResonanceDialog (#4735, Screen 6 of the approved demo) - move part of a thread's
 * resonance to another resonance (#5123: a thread holds several, on rows with amounts).
 *
 * One framed box headed "Thread: <name> · level <n> · <resonance>", a "Move from" row of the
 * thread's own resonances (when it holds more than one), a "Points to move" stepper (all of
 * the row by default), a "Change to" row of resonance pills, the component pills for the
 * chosen option, the points that land, and a right-aligned Retune thread button. The rite is
 * the authored retune ritual the options endpoint names. When the thread cannot move (no rite, an anchor that holds its
 * resonance, no options) the server's `unavailable_reason` stands in for the pills.
 * Offerings are picked only when the rite asks for them (`offering_required`), up to
 * `offering_count`. When the result names a different thread, that thread opens afterwards.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle, NO_DESCRIPTION } from '@/components/ui/dialog';
import { pillClass } from '../pillClass';
import { useRetuneThread, useThreadResonanceOptions } from '../../queries';
import type { ConversionType, Thread, ThreadResonanceOption } from '../../types';

const CONVERSION_TYPE_LABELS: Record<ConversionType, string> = {
  FALL: 'Fall',
  REDEMPTION: 'Redemption',
};

// The square marks what the move is (a retune, a Fall, a Redemption), the same on every thread.
const MOVE_SWATCHES: Record<ConversionType, string> = {
  FALL: 'bg-rose-500',
  REDEMPTION: 'bg-amber-500',
};
// A retune's square takes the pill's text colour, so it shows on the filled (selected) pill too.
const RETUNE_SWATCH = { selected: 'bg-primary-foreground', unselected: 'bg-primary' };

function swatchFor(option: ThreadResonanceOption, selected: boolean): string {
  if (option.conversion_type) return MOVE_SWATCHES[option.conversion_type];
  return selected ? RETUNE_SWATCH.selected : RETUNE_SWATCH.unselected;
}

function optionSuffix(option: ThreadResonanceOption): string {
  return option.conversion_type
    ? `(${CONVERSION_TYPE_LABELS[option.conversion_type]})`
    : '(same affinity)';
}

/** The surviving thread's id from a retune result, when the server sent one. */
function survivorId(result: Record<string, unknown> | undefined): number | null {
  const id = result?.thread_id;
  return typeof id === 'number' ? id : null;
}

interface ThreadResonanceDialogProps {
  thread: Thread;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ThreadResonanceDialog({ thread, open, onOpenChange }: ThreadResonanceDialogProps) {
  const retune = useRetuneThread();
  const navigate = useNavigate();
  const [pickedResonanceId, setPickedResonanceId] = useState<number | null>(null);
  const [componentIds, setComponentIds] = useState<number[]>([]);
  const rows = thread.resonances ?? [];
  const [fromId, setFromId] = useState<number | null>(null);
  // null = move all of the row.
  const [moveAmount, setMoveAmount] = useState<number | null>(null);

  const fromRow = rows.find((r) => r.resonance_id === fromId) ?? rows.find((r) => r.leads);
  const rowAmount = fromRow?.amount ?? thread.developed_points;
  const moving = moveAmount === null ? rowAmount : Math.min(moveAmount, rowAmount);
  const { data, isLoading, isError } = useThreadResonanceOptions(
    thread.id,
    open,
    fromRow ? { fromResonance: fromRow.resonance_id, amount: moveAmount } : undefined
  );

  const options = data?.options ?? [];
  const unavailableReason = data?.unavailable_reason ?? '';
  const selected = unavailableReason
    ? undefined
    : (options.find((o) => o.resonance_id === pickedResonanceId) ?? options[0]);
  const ritualId = data?.ritual_id ?? null;
  const offeringRequired = data?.offering_required ?? false;
  // A stack can pay several units, so fewer qualifying items than units may still pay;
  // the server refuses (and says why) when they do not.
  const picksNeeded = offeringRequired
    ? Math.min(data?.offering_count ?? 0, selected?.qualifying.length ?? 0)
    : 0;
  const canRetune =
    ritualId !== null &&
    selected !== undefined &&
    (!offeringRequired || (picksNeeded > 0 && componentIds.length === picksNeeded)) &&
    !retune.isPending;

  function pickFrom(resonanceId: number) {
    retune.reset();
    setFromId(resonanceId);
    setMoveAmount(null);
    setPickedResonanceId(null);
    setComponentIds([]);
  }

  function stepAmount(delta: number) {
    retune.reset();
    setMoveAmount(Math.max(1, Math.min(rowAmount, moving + delta)));
    setComponentIds([]);
  }

  function pickOption(resonanceId: number) {
    retune.reset();
    setPickedResonanceId(resonanceId);
    setComponentIds([]);
  }

  function toggleComponent(itemId: number) {
    retune.reset();
    setComponentIds((picked) => {
      if (picked.includes(itemId)) return picked.filter((id) => id !== itemId);
      if (picksNeeded === 1) return [itemId];
      if (picked.length >= picksNeeded) return picked;
      return [...picked, itemId];
    });
  }

  function handleRetune() {
    if (ritualId === null || !selected) return;
    retune.mutate(
      {
        character_sheet_id: thread.owner,
        ritual_id: ritualId,
        kwargs: {
          thread_id: thread.id,
          target_resonance: selected.resonance_id,
          ...(fromRow ? { from_resonance: fromRow.resonance_id } : {}),
          ...(moveAmount !== null ? { amount: moving } : {}),
        },
        components: offeringRequired ? componentIds : [],
      },
      {
        onSuccess: (result) => {
          toast.success(result.message ?? 'Thread retuned.');
          onOpenChange(false);
          const survivor = survivorId(result.result);
          if (survivor !== null && survivor !== thread.id) navigate(`/threads/${survivor}`);
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        {...NO_DESCRIPTION}
        className="max-h-[90vh] space-y-3 overflow-y-auto"
        data-testid="thread-resonance-dialog"
      >
        <DialogTitle className="text-sm font-semibold">
          Thread: {thread.name.trim() || '(unnamed)'} · level {thread.level} ·{' '}
          {thread.resonance_name}
        </DialogTitle>

        {isLoading ? <p className="text-sm text-muted-foreground">Loading…</p> : null}
        {isError ? (
          <p role="alert" className="text-sm text-destructive">
            Could not load the resonance options.
          </p>
        ) : null}

        {unavailableReason ? (
          <p role="status" className="text-sm" data-testid="resonance-unavailable">
            {unavailableReason}
          </p>
        ) : null}

        {rows.length > 1 ? (
          <div
            className="flex flex-wrap items-center gap-2"
            role="radiogroup"
            aria-label="Move from"
            data-testid="resonance-from"
          >
            <span className="text-sm text-muted-foreground">Move from</span>
            {rows.map((r) => (
              <button
                key={r.resonance_id}
                type="button"
                role="radio"
                aria-checked={r.resonance_id === fromRow?.resonance_id}
                onClick={() => pickFrom(r.resonance_id)}
                data-testid={`resonance-from-${r.resonance_id}`}
                className={pillClass(r.resonance_id === fromRow?.resonance_id)}
              >
                {r.resonance_name}
              </button>
            ))}
          </div>
        ) : null}

        {fromRow && rowAmount > 1 ? (
          <div className="flex flex-wrap items-center gap-2" data-testid="resonance-amount">
            <span className="text-sm text-muted-foreground">Points to move</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label="Move fewer points"
              onClick={() => stepAmount(-1)}
              disabled={moving <= 1}
              data-testid="resonance-amount-down"
            >
              -
            </Button>
            <span
              className="w-10 text-center font-medium tabular-nums"
              data-testid="resonance-amount-value"
            >
              {moving}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label="Move more points"
              onClick={() => stepAmount(1)}
              disabled={moving >= rowAmount}
              data-testid="resonance-amount-up"
            >
              +
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                retune.reset();
                setMoveAmount(null);
                setComponentIds([]);
              }}
              disabled={moveAmount === null}
              data-testid="resonance-amount-all"
            >
              All
            </Button>
          </div>
        ) : null}

        {selected ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-muted-foreground">Change to</span>
              {options.map((o) => (
                <button
                  key={o.resonance_id}
                  type="button"
                  aria-pressed={o.resonance_id === selected.resonance_id}
                  onClick={() => pickOption(o.resonance_id)}
                  data-testid={`resonance-option-${o.resonance_id}`}
                  className={`inline-flex items-center gap-1.5 ${pillClass(
                    o.resonance_id === selected.resonance_id
                  )}`}
                >
                  <span
                    aria-hidden="true"
                    data-testid={`resonance-swatch-${o.resonance_id}`}
                    className={`h-2.5 w-2.5 rounded-sm ${swatchFor(
                      o,
                      o.resonance_id === selected.resonance_id
                    )}`}
                  />
                  {o.resonance_name} {optionSuffix(o)}
                </button>
              ))}
            </div>

            {offeringRequired && selected.qualifying.length > 0 ? (
              <div className="flex flex-wrap gap-2" role="group" aria-label="Components">
                {selected.qualifying.map((c) => (
                  <button
                    key={c.item_id}
                    type="button"
                    aria-pressed={componentIds.includes(c.item_id)}
                    onClick={() => toggleComponent(c.item_id)}
                    data-testid={`resonance-component-${c.item_id}`}
                    className={pillClass(componentIds.includes(c.item_id))}
                  >
                    {c.name} · {c.mode}
                  </button>
                ))}
              </div>
            ) : null}
            {offeringRequired && selected.qualifying.length === 0 ? (
              <p role="status" className="text-sm" data-testid="resonance-no-offering">
                You carry no offering for {selected.resonance_name}.
              </p>
            ) : null}

            <p className="text-sm" data-testid="resonance-projected">
              {moving} points → {selected.projected_points}
            </p>
          </>
        ) : null}

        {retune.isError ? (
          <div
            role="alert"
            data-testid="resonance-error"
            className="rounded-md border border-red-600/60 bg-red-50 p-3 text-sm font-medium text-red-800 dark:bg-red-950/40 dark:text-red-200"
          >
            {retune.error?.message || 'The retune did not take; please try again.'}
          </div>
        ) : null}

        <div className="flex justify-end">
          <Button onClick={handleRetune} disabled={!canRetune} data-testid="resonance-retune">
            Retune thread
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
