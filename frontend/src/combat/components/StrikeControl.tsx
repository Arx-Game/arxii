/**
 * StrikeControl: the "With" row a picked Strike shows (#4858, slice 1 of #4844).
 *
 * Strike is the first pick in the Focused Action's pick row; once picked, this row sits
 * directly under it. Each weapon shows its gear kind and the strike skill its hit roll
 * uses; bare hands are always offered. The target is the Focused Action's own target
 * selection. The button dispatches the `combat_strike` registry action; the server
 * refuses what it cannot declare and the message shows inline.
 */

import { useEffect, useState } from 'react';

import { cn } from '@/lib/utils';
import type { components } from '@/generated/api';

export type StrikeWeaponOption = components['schemas']['StrikeWeaponOption'];

/** The value for bare hands, which have no item id. */
const BARE_HANDS_VALUE = 'bare';

export interface StrikeControlProps {
  weapons: StrikeWeaponOption[];
  /**
   * The weapon this round's declared Strike uses (null: bare hands), so a reload shows
   * what was declared; undefined when no Strike is declared.
   */
  declaredItemInstanceId?: number | null;
  /** The opponent picked in the Focused Action's target selection, if any. */
  targetOpponentId: number | null;
  /** The opponent this round's declared Strike is aimed at, when one is declared. */
  declaredTargetName: string | null;
  error: string | null;
  /** Every control is inert: locked, out of the declaring phase, or mid-dispatch. */
  disabled: boolean;
  pending: boolean;
  onStrike: (opponentId: number, itemInstanceId: number | null) => void;
}

function weaponValue(weapon: StrikeWeaponOption): string {
  return weapon.item_instance_id === null ? BARE_HANDS_VALUE : String(weapon.item_instance_id);
}

/** The pick for a declared Strike's weapon, or null when none is declared. */
function declaredWeaponValue(itemInstanceId: number | null | undefined): string | null {
  if (itemInstanceId === undefined) return null;
  return itemInstanceId === null ? BARE_HANDS_VALUE : String(itemInstanceId);
}

/** "one-handed melee · Melee Combat": the kind in sentence case, then the skill. */
function weaponChip(weapon: StrikeWeaponOption): string {
  return `${weapon.gear_kind.toLowerCase()} · ${weapon.strike_skill}`;
}

export function StrikeControl({
  weapons,
  declaredItemInstanceId,
  targetOpponentId,
  declaredTargetName,
  error,
  disabled,
  pending,
  onStrike,
}: StrikeControlProps) {
  const declaredValue = declaredWeaponValue(declaredItemInstanceId);
  const [weapon, setWeapon] = useState(
    () => declaredValue ?? (weapons[0] ? weaponValue(weapons[0]) : '')
  );

  // The weapon list arrives with the encounter and changes when gear does: keep the
  // choice while it is still offered, otherwise fall back to the first weapon.
  useEffect(() => {
    if (weapons.some((option) => weaponValue(option) === weapon)) return;
    const declared = weapons.find((option) => weaponValue(option) === declaredValue);
    const fallback = declared ?? weapons[0];
    setWeapon(fallback ? weaponValue(fallback) : '');
  }, [weapons, weapon, declaredValue]);

  const blocked = targetOpponentId === null || weapon === '';

  return (
    <div className="space-y-1.5" data-testid="strike-control">
      {declaredTargetName !== null && (
        <div
          className="rounded border border-orange-500/40 bg-orange-500/10 px-3 py-2 text-xs text-orange-300"
          data-testid="strike-declared-badge"
        >
          Striking {declaredTargetName}
        </div>
      )}
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
                'rounded border px-2.5 py-1 text-left text-xs transition-colors',
                'disabled:cursor-not-allowed disabled:opacity-50',
                selected
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border bg-background text-foreground hover:border-primary/50'
              )}
            >
              <span className="font-medium">{option.name}</span>
              <span className="ml-1.5 text-[10px] text-muted-foreground">{weaponChip(option)}</span>
            </button>
          );
        })}
      </div>
      <button
        type="button"
        disabled={disabled || blocked}
        onClick={() => {
          if (targetOpponentId === null) return;
          onStrike(targetOpponentId, weapon === BARE_HANDS_VALUE ? null : Number(weapon));
        }}
        data-testid="strike-confirm-btn"
        className={cn(
          'w-full rounded-md border px-4 py-1.5 text-xs font-semibold transition-colors',
          'disabled:cursor-not-allowed disabled:opacity-50',
          disabled || blocked
            ? 'border-border bg-muted text-muted-foreground'
            : 'border-primary bg-primary/10 text-primary hover:bg-primary/20'
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
