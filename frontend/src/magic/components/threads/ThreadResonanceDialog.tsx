/**
 * ThreadResonanceDialog (#4735, Screen 6 of the approved demo) - move a thread to
 * another resonance.
 *
 * One framed box headed "Thread: <name> · level <n> · <resonance>", a "Change to" row of
 * resonance pills, the component pills for the chosen option, the points the thread keeps,
 * and a right-aligned Retune thread button. The rite is the authored retune ritual the
 * options endpoint names. When the thread cannot move (no rite, an anchor that holds its
 * resonance, no options) the server's `unavailable_reason` stands in for the pills.
 * Offerings are picked only when the rite asks for them (`offering_required`), up to
 * `offering_count`. A move that merges into another thread opens the survivor afterwards.
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
const RETUNE_SWATCH = 'bg-primary';

function swatchFor(option: ThreadResonanceOption): string {
  return option.conversion_type ? MOVE_SWATCHES[option.conversion_type] : RETUNE_SWATCH;
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
  const { data, isLoading, isError } = useThreadResonanceOptions(thread.id, open);
  const retune = useRetuneThread();
  const navigate = useNavigate();
  const [pickedResonanceId, setPickedResonanceId] = useState<number | null>(null);
  const [componentIds, setComponentIds] = useState<number[]>([]);

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
        kwargs: { thread_id: thread.id, target_resonance: selected.resonance_id },
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
          Thread: {thread.name.trim() || '(unnamed)'} · level {thread.level / 10} ·{' '}
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
                  <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-sm ${swatchFor(o)}`} />
                  {o.resonance_name} {optionSuffix(o)}
                  {o.merges_into_thread_id !== null ? (
                    <span
                      className="rounded-sm border border-current px-1 text-xs"
                      data-testid={`resonance-merges-${o.resonance_id}`}
                    >
                      merges
                    </span>
                  ) : null}
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

            <p className="text-sm" data-testid="resonance-projected">
              {thread.developed_points} points → {selected.projected_points}
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
