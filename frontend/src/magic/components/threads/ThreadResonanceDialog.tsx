/**
 * ThreadResonanceDialog (#4735, Screen 6 of the approved demo) - move a thread to
 * another resonance.
 *
 * One framed box headed "Thread: <name> · level <n> · <resonance>", a "Change to" row of
 * resonance pills, the component pills for the chosen option, the points the thread keeps,
 * and a right-aligned Retune thread button. The rite is the authored retune ritual the
 * options endpoint names; with none authored the button stays disabled.
 */
import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle, NO_DESCRIPTION } from '@/components/ui/dialog';
import { pillClass } from '../pillClass';
import { useRetuneThread, useThreadResonanceOptions } from '../../queries';
import type { Thread, ThreadResonanceOption } from '../../types';

const CONVERSION_TYPE_LABELS: Record<string, string> = {
  FALL: 'Fall',
  REDEMPTION: 'Redemption',
};

// Affinity squares take a palette slot by order of first appearance, so no affinity is named in code.
const AFFINITY_SWATCHES = [
  'bg-sky-500',
  'bg-rose-500',
  'bg-amber-500',
  'bg-emerald-500',
  'bg-violet-500',
];

function optionSuffix(option: ThreadResonanceOption): string {
  if (option.conversion_type === null) return '(same affinity)';
  return `(${CONVERSION_TYPE_LABELS[option.conversion_type] ?? option.conversion_type})`;
}

interface ThreadResonanceDialogProps {
  thread: Thread;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ThreadResonanceDialog({ thread, open, onOpenChange }: ThreadResonanceDialogProps) {
  const { data, isLoading, isError } = useThreadResonanceOptions(thread.id, open);
  const retune = useRetuneThread();
  const [pickedResonanceId, setPickedResonanceId] = useState<number | null>(null);
  const [componentId, setComponentId] = useState<number | null>(null);

  const options = data?.options ?? [];
  const selected = options.find((o) => o.resonance_id === pickedResonanceId) ?? options[0];
  const affinities = Array.from(new Set(options.map((o) => o.affinity_name)));
  const ritualId = data?.ritual_id ?? null;
  const needsComponent = (selected?.qualifying.length ?? 0) > 0;
  const canRetune =
    ritualId !== null &&
    selected !== undefined &&
    (!needsComponent || componentId !== null) &&
    !retune.isPending;

  function pickOption(resonanceId: number) {
    retune.reset();
    setPickedResonanceId(resonanceId);
    setComponentId(null);
  }

  function handleRetune() {
    if (ritualId === null || !selected) return;
    retune.mutate(
      {
        character_sheet_id: thread.owner,
        ritual_id: ritualId,
        kwargs: { thread_id: thread.id, target_resonance: selected.resonance_id },
        components: componentId === null ? [] : [componentId],
      },
      {
        onSuccess: (result) => {
          toast.success(result.message ?? 'Thread retuned.');
          onOpenChange(false);
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
                    className={`h-2.5 w-2.5 rounded-sm ${
                      AFFINITY_SWATCHES[
                        affinities.indexOf(o.affinity_name) % AFFINITY_SWATCHES.length
                      ]
                    }`}
                  />
                  {o.resonance_name} {optionSuffix(o)}
                </button>
              ))}
            </div>

            {needsComponent ? (
              <div className="flex flex-wrap gap-2" role="group" aria-label="Components">
                {selected.qualifying.map((c) => (
                  <button
                    key={c.item_id}
                    type="button"
                    aria-pressed={componentId === c.item_id}
                    onClick={() => setComponentId(c.item_id)}
                    data-testid={`resonance-component-${c.item_id}`}
                    className={pillClass(componentId === c.item_id)}
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
