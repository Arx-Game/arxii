/**
 * Resonance burn helpers for the Strain area (#4736). Mirrors the server's rounding:
 * the burn is capped at the preview ceiling and its strain units are floored.
 */

import type { BurnPreview } from './types';

/** The burn state a Strain area renders: the preview plus the chosen amount. */
export interface StrainBurn {
  /** Burn numbers from the pull preview; null hides the input. */
  preview: BurnPreview | null;
  value: number;
  onChange: (next: number) => void;
  /** Tier of the pull, for the ceiling line when the preview names no intensity tier. */
  tier?: number;
  /**
   * The pulled resonances, when the pull mixes several (#5066): the player picks which
   * one burns. Omitted or a single entry: the pull's one resonance burns.
   */
  resonances?: { id: number; name: string }[];
  /** The resonance chosen to burn, from ``resonances``; null until one is picked. */
  resonanceId?: number | null;
  onResonanceChange?: (id: number) => void;
}

/** The distinct resonances of the pulled threads, in thread order (#5066). */
export function pulledResonances(
  threads: { resonance: number; resonance_name: string }[]
): { id: number; name: string }[] {
  const seen = new Map<number, string>();
  for (const thread of threads) {
    if (!seen.has(thread.resonance)) seen.set(thread.resonance, thread.resonance_name);
  }
  return [...seen].map(([id, name]) => ({ id, name }));
}

/**
 * The resonance a burn on a pull comes from: the chosen one while it is still pulled,
 * else the pull's only resonance, else null (a mixed pull must name one).
 */
export function burnResonanceFor(
  resonances: { id: number }[],
  chosen: number | null
): number | null {
  if (chosen !== null && resonances.some((r) => r.id === chosen)) return chosen;
  return resonances.length === 1 ? resonances[0].id : null;
}

/** Strain units ``value`` burned points add to the strain curve. */
export function burnStrainUnits(preview: BurnPreview | null, value: number): number {
  if (!preview || !preview.available || value <= 0) return 0;
  return Math.floor(value * Number(preview.strain_units_per_point));
}

/** The burn that will be sent: the chosen amount, never past the ceiling. */
export function effectiveBurn(preview: BurnPreview | null, value: number): number {
  if (!preview || !preview.available) return 0;
  return Math.max(Math.min(value, preview.ceiling), 0);
}
