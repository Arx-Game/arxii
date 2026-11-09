/**
 * StrikeControl: the "With" and "Enchant with" rows a picked Strike shows (#4858, #5026).
 *
 * Strike is the first pick in the Focused Action's pick row; once picked, these rows sit
 * directly under it. Each weapon shows its gear kind and the strike skill its hit roll
 * uses; a weapon that can be thrown is offered twice, to strike and to throw, the throw
 * naming its damage share. Bare hands are always offered. "Enchant with" lists the
 * character's weapon techniques with their anima cost, plus "No enchantment"; picking one
 * casts it into this Strike, paid on the attack. A cast carrying a Soulfray warning shows
 * the accept box, and Strike waits for it. The target is the Focused Action's own target
 * selection. The button dispatches the `combat_strike` registry action; the server refuses
 * what it cannot declare and the message shows inline.
 */

import { useEffect, useState } from 'react';

import { cn } from '@/lib/utils';
import type { components } from '@/generated/api';
import type { PlayerAction } from '@/scenes/actionTypes';
import { SoulfrayAcceptGate } from './SoulfrayAcceptGate';

export type StrikeWeaponOption = components['schemas']['StrikeWeaponOption'];

/** The value for bare hands, which have no item id. */
const BARE_HANDS_VALUE = 'bare';
/** The value for "No enchantment". */
const NO_ENCHANTMENT = 'none';

/** What the Strike button sends: the weapon, how it is used, and the enchantment. */
export interface StrikeChoice {
  itemInstanceId: number | null;
  thrown: boolean;
  techniqueId: number | null;
  confirmSoulfrayRisk: boolean;
}

export interface StrikeControlProps {
  weapons: StrikeWeaponOption[];
  /** The character's weapon techniques, cast into a Strike (#5026). */
  enchantments?: PlayerAction[];
  /**
   * The weapon this round's declared Strike uses (null: bare hands), so a reload shows
   * what was declared; undefined when no Strike is declared.
   */
  declaredItemInstanceId?: number | null;
  /** Whether this round's declared Strike throws its weapon. */
  declaredThrown?: boolean;
  /** The technique cast into this round's declared Strike, if any. */
  declaredTechniqueId?: number | null;
  /** The opponent picked in the Focused Action's target selection, if any. */
  targetOpponentId: number | null;
  /** "Bandit archer · 2 positions away": the picked target and how far it stands. */
  targetSummary?: string | null;
  /** The opponent this round's declared Strike is aimed at, when one is declared. */
  declaredTargetName: string | null;
  error: string | null;
  /** Every control is inert: locked, out of the declaring phase, or mid-dispatch. */
  disabled: boolean;
  pending: boolean;
  onStrike: (opponentId: number, choice: StrikeChoice) => void;
}

function weaponValue(weapon: StrikeWeaponOption): string {
  if (weapon.item_instance_id === null) return BARE_HANDS_VALUE;
  return weapon.thrown ? `${weapon.item_instance_id}-thrown` : String(weapon.item_instance_id);
}

/** The pick for a declared Strike's weapon, or null when none is declared. */
function declaredWeaponValue(
  itemInstanceId: number | null | undefined,
  thrown: boolean | undefined
): string | null {
  if (itemInstanceId === undefined) return null;
  if (itemInstanceId === null) return BARE_HANDS_VALUE;
  return thrown ? `${itemInstanceId}-thrown` : String(itemInstanceId);
}

/**
 * "one-handed melee · Melee Combat": the kind in sentence case, then the skill; a throw
 * reads "Thrown Combat · 75% damage".
 */
function weaponChip(weapon: StrikeWeaponOption): string {
  if (weapon.thrown) {
    const share = weapon.damage_share !== null ? ` · ${weapon.damage_share}% damage` : '';
    return `${weapon.strike_skill}${share}`;
  }
  return `${weapon.gear_kind.toLowerCase()} · ${weapon.strike_skill}`;
}

/** "fire · 4 anima": what an enchantment adds and what it costs on this attack. */
function enchantmentChip(action: PlayerAction): string {
  const types = (action.enchant_damage_types ?? []).join(', ');
  const cost = action.cast_preview?.effective_anima_cost;
  const costText = cost !== undefined ? `${cost} anima` : '';
  return [types, costText].filter((part) => part !== '').join(' · ');
}

function enchantmentValue(action: PlayerAction): string {
  return String(action.ref.technique_id);
}

export function StrikeControl({
  weapons,
  enchantments = [],
  declaredItemInstanceId,
  declaredThrown,
  declaredTechniqueId,
  targetOpponentId,
  targetSummary = null,
  declaredTargetName,
  error,
  disabled,
  pending,
  onStrike,
}: StrikeControlProps) {
  const declaredValue = declaredWeaponValue(declaredItemInstanceId, declaredThrown);
  const [weapon, setWeapon] = useState(
    () => declaredValue ?? (weapons[0] ? weaponValue(weapons[0]) : '')
  );
  const [enchantment, setEnchantment] = useState(() =>
    declaredTechniqueId != null ? String(declaredTechniqueId) : NO_ENCHANTMENT
  );
  const [soulfrayAccepted, setSoulfrayAccepted] = useState(false);

  // The weapon list arrives with the encounter and changes when gear does: keep the
  // choice while it is still offered, otherwise fall back to the first weapon.
  useEffect(() => {
    if (weapons.some((option) => weaponValue(option) === weapon)) return;
    const declared = weapons.find((option) => weaponValue(option) === declaredValue);
    const fallback = declared ?? weapons[0];
    setWeapon(fallback ? weaponValue(fallback) : '');
  }, [weapons, weapon, declaredValue]);

  const chosen = weapons.find((option) => weaponValue(option) === weapon);
  const chosenEnchantment = enchantments.find((a) => enchantmentValue(a) === enchantment);
  const warning = chosenEnchantment?.soulfray_warning ?? null;
  const blocked =
    targetOpponentId === null || chosen === undefined || (warning !== null && !soulfrayAccepted);

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
      {targetSummary !== null && (
        <p className="text-xs text-muted-foreground" data-testid="strike-target">
          Target: <span className="font-medium text-foreground">{targetSummary}</span>
        </p>
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
              <span className="font-medium">
                {option.name}
                {option.thrown ? ', thrown' : ''}
              </span>
              <span className="ml-1.5 text-[10px] text-muted-foreground">{weaponChip(option)}</span>
            </button>
          );
        })}
      </div>
      {enchantments.length > 0 && (
        <>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Enchant with
          </p>
          <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Enchant with">
            {[null, ...enchantments].map((action) => {
              const value = action === null ? NO_ENCHANTMENT : enchantmentValue(action);
              const selected = value === enchantment;
              return (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  disabled={disabled}
                  onClick={() => {
                    setEnchantment(value);
                    setSoulfrayAccepted(false);
                  }}
                  data-testid={`strike-enchant-${value}`}
                  className={cn(
                    'rounded border px-2.5 py-1 text-left text-xs transition-colors',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                    selected
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border bg-background text-foreground hover:border-primary/50'
                  )}
                >
                  <span className="font-medium">
                    {action === null ? 'No enchantment' : action.display_name}
                  </span>
                  <span className="ml-1.5 text-[10px] text-muted-foreground">
                    {action === null ? 'a plain Strike' : enchantmentChip(action)}
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}
      {chosenEnchantment && warning !== null && (
        <SoulfrayAcceptGate
          warning={warning}
          techniqueName={chosenEnchantment.display_name}
          animaCost={chosenEnchantment.cast_preview?.effective_anima_cost ?? null}
          accepted={soulfrayAccepted}
          onAcceptChange={setSoulfrayAccepted}
          disabled={disabled}
        />
      )}
      <button
        type="button"
        disabled={disabled || blocked}
        onClick={() => {
          if (targetOpponentId === null || chosen === undefined) return;
          onStrike(targetOpponentId, {
            itemInstanceId: chosen.item_instance_id,
            thrown: chosen.thrown,
            techniqueId: chosenEnchantment?.ref.technique_id ?? null,
            confirmSoulfrayRisk: chosenEnchantment !== undefined && soulfrayAccepted,
          });
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
