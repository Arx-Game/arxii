/**
 * StrikeControl: declare a basic Strike (#4858, slice 1 of #4844).
 *
 * Any character can Strike an opponent with no technique: with one of their equipped
 * weapons, or bare hands. The weapon choices come from the viewer's own participant
 * (`strike_weapons`), each showing its gear kind and the strike skill its hit roll uses.
 * Dispatches the `combat_strike` registry action; the server refuses what it cannot
 * declare and the message shows inline. The Strike is the round's one action.
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
import type { components } from '@/generated/api';

export type StrikeWeaponOption = components['schemas']['StrikeWeaponOption'];

/** The select value for bare hands, which have no item id. */
const BARE_HANDS_VALUE = 'bare';

export interface StrikeOpponent {
  id: number;
  name: string;
}

export interface StrikeControlProps {
  weapons: StrikeWeaponOption[];
  opponents: StrikeOpponent[];
  /** The opponent this round's declared Strike is aimed at, when one is declared. */
  declaredTargetName: string | null;
  error: string | null;
  /** Every control is inert: locked, out of the declaring phase, or mid-dispatch. */
  disabled: boolean;
  /** Locked or out of phase, ignoring dispatch; drives the button styling. */
  inactive: boolean;
  pending: boolean;
  onStrike: (opponentId: number, itemInstanceId: number | null) => void;
}

function weaponValue(weapon: StrikeWeaponOption): string {
  return weapon.item_instance_id === null ? BARE_HANDS_VALUE : String(weapon.item_instance_id);
}

export function StrikeControl({
  weapons,
  opponents,
  declaredTargetName,
  error,
  disabled,
  inactive,
  pending,
  onStrike,
}: StrikeControlProps) {
  const [opponentId, setOpponentId] = useState('');
  const [weapon, setWeapon] = useState(() => (weapons[0] ? weaponValue(weapons[0]) : ''));

  if (weapons.length === 0 || opponents.length === 0) return null;

  const blocked = opponentId === '' || weapon === '';

  return (
    <div
      className="space-y-1.5 rounded border border-border bg-card/60 p-2"
      data-testid="strike-control"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Strike</p>
      {declaredTargetName !== null && (
        <div
          className="rounded border border-orange-500/40 bg-orange-500/10 px-3 py-2 text-xs text-orange-300"
          data-testid="strike-declared-badge"
        >
          Striking {declaredTargetName}
        </div>
      )}
      <Select value={opponentId} onValueChange={setOpponentId} disabled={disabled}>
        <SelectTrigger data-testid="strike-opponent-select" className="h-8 text-xs">
          <SelectValue placeholder="Strike at…" />
        </SelectTrigger>
        <SelectContent>
          {opponents.map((opponent) => (
            <SelectItem key={opponent.id} value={String(opponent.id)}>
              {opponent.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        With
      </p>
      <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Strike with">
        {weapons.map((option) => {
          const value = weaponValue(option);
          const selected = value === weapon;
          return (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={disabled}
              onClick={() => setWeapon(value)}
              data-testid={`strike-weapon-${value}`}
              className={cn(
                'rounded border px-2 py-1 text-left text-xs transition-colors',
                'disabled:cursor-not-allowed disabled:opacity-50',
                selected
                  ? 'border-orange-500/60 bg-orange-500/10 text-orange-300'
                  : 'border-border text-foreground hover:bg-muted/40'
              )}
            >
              <span className="font-semibold capitalize">{option.name}</span>
              <span className="ml-1.5 text-[10px] text-muted-foreground">
                {option.gear_kind} · {option.strike_skill}
              </span>
            </button>
          );
        })}
      </div>
      <button
        type="button"
        disabled={disabled || blocked}
        onClick={() =>
          onStrike(Number(opponentId), weapon === BARE_HANDS_VALUE ? null : Number(weapon))
        }
        data-testid="strike-confirm-btn"
        className={cn(
          'w-full rounded-md border px-4 py-1.5 text-xs font-semibold transition-colors',
          'disabled:cursor-not-allowed disabled:opacity-50',
          inactive || blocked
            ? 'border-border bg-muted text-muted-foreground'
            : 'border-orange-500/60 bg-orange-500/10 text-orange-300 hover:bg-orange-500/20'
        )}
      >
        {pending ? 'Declaring…' : 'Strike'}
      </button>
      {error !== null && (
        <p role="alert" className="text-sm text-destructive" data-testid="strike-error">
          {error}
        </p>
      )}
    </div>
  );
}
