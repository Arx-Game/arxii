/**
 * WaitingStrikeControl — declare a waiting strike (#4608, slice 3 of #4576).
 *
 * The waiting strike holds one melee technique for the first enemy that comes into
 * reach or attacks; it is the round's one action. Dispatches the `combat_await_opening`
 * registry action. Backend-trusting like the Charge control: the server refuses a
 * technique it cannot hold and the message shows inline.
 */

import { useState } from 'react';

import { cn } from '@/lib/utils';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { PlayerAction } from '@/scenes/actionTypes';
import { SoulfrayAcceptGate } from './SoulfrayAcceptGate';

export interface WaitingStrikeControlProps {
  techniques: PlayerAction[];
  /** The technique held this round, when a waiting strike is already declared. */
  declaredTechniqueName: string | null;
  error: string | null;
  /** Every control is inert: locked, out of the declaring phase, or mid-dispatch. */
  disabled: boolean;
  /** Locked or out of phase, ignoring dispatch — drives the button styling. */
  inactive: boolean;
  pending: boolean;
  onDeclare: (techniqueId: number, confirmSoulfrayRisk: boolean) => void;
}

export function WaitingStrikeControl({
  techniques,
  declaredTechniqueName,
  error,
  disabled,
  inactive,
  pending,
  onDeclare,
}: WaitingStrikeControlProps) {
  const [techniqueId, setTechniqueId] = useState('');
  const [soulfrayAccepted, setSoulfrayAccepted] = useState(false);

  if (techniques.length === 0) return null;

  const selected = techniques.find((a) => String(a.ref.technique_id) === techniqueId);
  const warning = selected?.soulfray_warning ?? null;
  const blocked = techniqueId === '' || (warning !== null && !soulfrayAccepted);

  return (
    <div
      className="space-y-1.5 rounded border border-border bg-card/60 p-2"
      data-testid="waiting-strike-control"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Wait for an Opening
      </p>
      {declaredTechniqueName !== null && (
        <div
          className="rounded border border-teal-500/40 bg-teal-500/10 px-3 py-2 text-xs text-teal-300"
          data-testid="waiting-strike-declared-badge"
        >
          Waiting for an opening: {declaredTechniqueName}
        </div>
      )}
      <Select
        value={techniqueId}
        onValueChange={(value) => {
          setTechniqueId(value);
          setSoulfrayAccepted(false);
        }}
        disabled={disabled}
      >
        <SelectTrigger data-testid="waiting-strike-technique-select" className="h-8 text-xs">
          <SelectValue placeholder="Strike with…" />
        </SelectTrigger>
        <SelectContent>
          {techniques.map((action) => (
            <SelectItem
              key={action.ref.technique_id ?? action.display_name}
              value={String(action.ref.technique_id)}
            >
              {action.display_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {selected && warning !== null && (
        <SoulfrayAcceptGate
          warning={warning}
          techniqueName={selected.display_name}
          animaCost={0}
          accepted={soulfrayAccepted}
          onAcceptChange={setSoulfrayAccepted}
          disabled={disabled}
        />
      )}
      <button
        type="button"
        disabled={disabled || blocked}
        onClick={() => onDeclare(Number(techniqueId), soulfrayAccepted)}
        data-testid="waiting-strike-confirm-btn"
        className={cn(
          'w-full rounded-md border px-4 py-1.5 text-xs font-semibold transition-colors',
          'disabled:cursor-not-allowed disabled:opacity-50',
          inactive || blocked
            ? 'border-border bg-muted text-muted-foreground'
            : 'border-teal-500/60 bg-teal-500/10 text-teal-300 hover:bg-teal-500/20'
        )}
      >
        {pending ? 'Declaring…' : 'Wait for an opening'}
      </button>
      {error !== null && (
        <p role="alert" className="text-sm text-destructive" data-testid="waiting-strike-error">
          {error}
        </p>
      )}
    </div>
  );
}
