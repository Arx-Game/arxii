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
