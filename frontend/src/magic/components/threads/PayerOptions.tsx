/**
 * PayerOptions (#5123, Screen 2 of the approved demo): the resonances that can pay for one
 * pulled thread, each with its cost, what you hold, and the perks it would give on this
 * thread. A thread holding several resonances shows the choice and starts on its leading
 * one; a thread with one resonance shows what it pays with and no choice, unless its own
 * resonance cannot pay, when any held resonance may.
 *
 * Each pulled thread is paid for by one resonance, so the effects here are that payer's alone
 * and are never summed across threads. A held resonance the thread never took in pays an
 * ordinary pull and lists no perks.
 */
import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import {
  defaultPayerId,
  effectLabel,
  effectValue,
  showsPayerChoice,
  threadMixInWords,
} from '../../burn';
import type { PayerOption, Thread } from '../../types';
import { PerkInspect } from './PerkInspect';

interface PayerOptionsProps {
  thread: Thread;
  /** The thread's payer options from the pull preview, one per resonance the player holds. */
  options: PayerOption[];
  /** The resonance the player picked to pay; undefined until they pick. */
  selectedResonanceId: number | undefined;
  /** The player picked a payer. */
  onSelect: (resonanceId: number) => void;
  /**
   * The payer the pull has to name for this thread, or null for none. It is the picked (or
   * starting) payer while the choice is shown and that payer is not the leading resonance;
   * with no choice shown, or on the leader, it is null, so a pick made where the choice was
   * shown never outlives it. Nothing is reported when the list unmounts: a thread whose row is
   * only hidden (a name filter) is still pulled, and the pulls filter to the threads still
   * pulled themselves.
   */
  onResolve?: (resonanceId: number | null) => void;
}

function PerkRows({ thread, option }: { thread: Thread; option: PayerOption }) {
  if (option.effects.length === 0) {
    return (
      <p className="text-xs text-muted-foreground" data-testid={`payer-no-perks-${thread.id}`}>
        No perks on this thread
      </p>
    );
  }
  return (
    <ul
      className="space-y-0.5 text-xs"
      data-testid={`payer-perks-${thread.id}-${option.resonance_id}`}
    >
      {option.effects.map((effect, index) => (
        <li
          key={`${effect.kind}-${index}`}
          className={cn('flex flex-wrap items-baseline gap-x-2', effect.inactive && 'opacity-50')}
        >
          <span>{effectLabel(effect)}</span>
          <span className="font-medium tabular-nums">{effectValue(effect)}</span>
          {effect.narrative_snippet && (
            <span className="italic text-muted-foreground">{effect.narrative_snippet}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

function costLine(option: PayerOption): string {
  return `${option.cost} ${option.resonance_name} · you have ${option.balance}`;
}

/** The one-line "Level 3 · mostly Fury, some Domination" a thread's makeup reads as. */
export function ThreadMakeup({ thread }: { thread: Thread }) {
  // A thread of one resonance is named by its anchor line; the mix is for several.
  const rows = thread.resonances ?? [];
  const mix = rows.length > 1 ? threadMixInWords(rows) : '';
  return (
    <span className="text-xs text-muted-foreground" data-testid={`thread-makeup-${thread.id}`}>
      Level {thread.level}
      {mix ? ` · ${mix}` : ''}
    </span>
  );
}

export function PayerOptions({
  thread,
  options,
  selectedResonanceId,
  onSelect,
  onResolve,
}: PayerOptionsProps) {
  const [inspecting, setInspecting] = useState<PayerOption | null>(null);
  const hasChoice = showsPayerChoice(thread, options);
  const startingId = defaultPayerId(thread, options);
  const picked =
    selectedResonanceId !== undefined && options.some((o) => o.resonance_id === selectedResonanceId)
      ? selectedResonanceId
      : undefined;
  const chosenId = picked ?? startingId;
  const toSend = hasChoice && chosenId !== thread.resonance ? chosenId : null;

  // Report what the pull has to name; only the latest callback is called, so a new inline
  // function each render does not re-run this.
  const resolveRef = useRef(onResolve);
  useEffect(() => {
    resolveRef.current = onResolve;
  });
  useEffect(() => {
    resolveRef.current?.(toSend);
  }, [toSend]);

  // A thread with one resonance pays with it; show that payer alone, no choice.
  if (!hasChoice) {
    const payer = options.find((o) => o.resonance_id === thread.resonance) ?? options[0];
    if (!payer) return null;
    return (
      <div className="space-y-1" data-testid={`payer-fixed-${thread.id}`}>
        <div className="flex flex-wrap justify-between gap-2 text-xs">
          <span>Pays with {payer.resonance_name}</span>
          <span className="tabular-nums">{costLine(payer)}</span>
        </div>
        <PerkRows thread={thread} option={payer} />
      </div>
    );
  }

  return (
    <div className="space-y-1.5" data-testid={`payer-options-${thread.id}`}>
      <span
        id={`payer-label-${thread.id}`}
        className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground"
      >
        Pay with
      </span>
      <div role="radiogroup" aria-labelledby={`payer-label-${thread.id}`} className="space-y-1.5">
        {options.map((option) => {
          const selected = option.resonance_id === chosenId;
          return (
            <div
              key={option.resonance_id}
              className={cn(
                'space-y-1 rounded-md border p-2',
                selected ? 'border-primary bg-primary/5' : 'border-border',
                !option.affordable && 'opacity-60'
              )}
            >
              <button
                type="button"
                role="radio"
                aria-checked={selected}
                disabled={!option.affordable}
                onClick={() => onSelect(option.resonance_id)}
                data-testid={`payer-${thread.id}-${option.resonance_id}`}
                className="flex w-full flex-wrap items-center justify-between gap-2 text-left text-sm disabled:cursor-not-allowed"
              >
                <span className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className={cn(
                      'inline-block h-3 w-3 rounded-full border',
                      selected ? 'border-primary bg-primary' : 'border-muted-foreground'
                    )}
                  />
                  <b>{option.resonance_name}</b>
                </span>
                <span className="text-xs tabular-nums">{costLine(option)}</span>
              </button>
              <PerkRows thread={thread} option={option} />
              {option.effects.length > 0 && (
                <button
                  type="button"
                  onClick={() => setInspecting(option)}
                  data-testid={`payer-inspect-${thread.id}-${option.resonance_id}`}
                  className="text-xs text-primary/80 underline-offset-2 hover:text-primary hover:underline"
                >
                  Inspect perks
                </button>
              )}
            </div>
          );
        })}
      </div>
      {inspecting && (
        <PerkInspect
          thread={thread}
          option={inspecting}
          open
          onOpenChange={(open) => {
            if (!open) setInspecting(null);
          }}
        />
      )}
    </div>
  );
}
