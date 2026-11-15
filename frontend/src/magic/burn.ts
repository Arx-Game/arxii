/**
 * Resonance burn helpers for the Strain area (#4736). Mirrors the server's rounding:
 * the burn is capped at the preview ceiling and its strain units are floored.
 */

import { shareInWords } from './aura';
import type { BurnPreview, PayerOption, PreviewedEffect, Thread } from './types';

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

/** The part of a thread the pull helpers read: its leading resonance and its rows. */
export interface PulledThread {
  id?: number;
  resonance: number;
  resonance_name: string;
  resonances?: { resonance_id: number; resonance_name: string }[];
}

/** The resonance paying for ``thread``: the player's pick, else its leading resonance (#5123). */
export function payerFor(
  thread: { id?: number; resonance: number },
  payers: Record<number, number>
): number {
  return (thread.id === undefined ? undefined : payers[thread.id]) ?? thread.resonance;
}

function payerName(
  thread: PulledThread,
  payerId: number,
  nameOf?: (id: number) => string | undefined
): string {
  if (payerId === thread.resonance) return thread.resonance_name;
  const row = (thread.resonances ?? []).find((r) => r.resonance_id === payerId);
  return row?.resonance_name ?? nameOf?.(payerId) ?? `Resonance #${payerId}`;
}

/**
 * The distinct resonances paying for the pulled threads, in thread order (#5066). With a
 * ``payers`` map (thread id to resonance id, #5123) a thread is paid by its pick; a thread
 * left out is paid by its leading resonance. ``nameOf`` names a payer that is not one of
 * the thread's own rows.
 */
export function pulledResonances(
  threads: PulledThread[],
  payers: Record<number, number> = {},
  nameOf?: (id: number) => string | undefined
): { id: number; name: string }[] {
  const seen = new Map<number, string>();
  for (const thread of threads) {
    const payerId = payerFor(thread, payers);
    if (!seen.has(payerId)) seen.set(payerId, payerName(thread, payerId, nameOf));
  }
  return [...seen].map(([id, name]) => ({ id, name }));
}

/**
 * A thread's resonance mix in words, never numbers: "mostly Fury, some Domination". A
 * thread with one resonance names it alone. The words come from `shareInWords`, the same
 * thresholds the aura reads: the leader is "mostly" once it is most of the thread, another
 * resonance is "some", or "a little" when it is a trace.
 */
export function threadMixInWords(
  rows: { resonance_name: string; amount: number; leads: boolean }[]
): string {
  const held = rows.filter((row) => row.amount > 0 || row.leads);
  if (held.length === 0) return '';
  if (held.length === 1) return held[0].resonance_name;
  const total = held.reduce((sum, row) => sum + row.amount, 0);
  const ordered = [...held].sort(
    (a, b) => Number(b.leads) - Number(a.leads) || b.amount - a.amount
  );
  return ordered
    .map((row, index) => {
      const words = shareInWords(row.amount, total);
      if (index === 0) {
        return words === 'most' || words === 'nearly all'
          ? `mostly ${row.resonance_name}`
          : row.resonance_name;
      }
      return `${words === 'a trace' ? 'a little' : 'some'} ${row.resonance_name}`;
    })
    .join(', ');
}

/**
 * Whether the player picks who pays a pulled thread: when it holds several resonances, or
 * when its own resonance cannot pay the cost (any held resonance may pay, so the player
 * must be able to name another). A thread of one resonance that can pay itself shows no
 * choice.
 */
export function showsPayerChoice(
  thread: { resonance: number; resonances?: unknown[] },
  options: { resonance_id: number; affordable: boolean }[]
): boolean {
  if ((thread.resonances ?? []).length > 1) return true;
  const own = options.find((o) => o.resonance_id === thread.resonance);
  return own !== undefined && !own.affordable;
}

/**
 * The payer a thread starts on: its leading resonance, or the first one that can pay when
 * the leader cannot. With no payer able to afford it, the leader, so the shortfall shows
 * on the leading resonance's own row.
 */
export function defaultPayerId(
  thread: { resonance: number },
  options: { resonance_id: number; affordable: boolean }[]
): number {
  const own = options.find((o) => o.resonance_id === thread.resonance);
  if (own === undefined || own.affordable) return thread.resonance;
  return options.find((o) => o.affordable)?.resonance_id ?? thread.resonance;
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

// ---------------------------------------------------------------------------
// Perk rows (#5123): how a payer's effects read on a pulled thread
// ---------------------------------------------------------------------------

const EFFECT_LABELS: Record<string, string> = {
  FLAT_BONUS: 'Bonus to this cast',
  INTENSITY_BUMP: 'Intensity',
  VITAL_BONUS: 'Bonus to a vital',
  CAPABILITY_GRANT: 'Grants a capability',
  RESISTANCE: 'Resistance',
  NARRATIVE_ONLY: 'Flavor',
};

export function perkWords(raw: string): string {
  const spaced = raw.replace(/_/g, ' ').toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * The label a perk row carries: what it does, in play words. A capability perk names the
 * capability it grants and a resistance names the damage type, so the row says the actual
 * effect.
 */
export function effectLabel(effect: PreviewedEffect): string {
  if (effect.kind === 'CAPABILITY_GRANT') {
    return effect.capability_name ? `Grants ${effect.capability_name}` : 'Grants a capability';
  }
  if (effect.kind === 'RESISTANCE') {
    return `Resistance to ${effect.resistance_damage_type_name ?? 'all damage'}`;
  }
  const base = EFFECT_LABELS[effect.kind] ?? perkWords(effect.kind);
  return effect.vital_target ? `${base}: ${perkWords(effect.vital_target)}` : base;
}

/**
 * The value a perk row carries. A capability perk carries its curved magnitude; a perk
 * with no number (flavor only) has none.
 */
export function effectValue(effect: PreviewedEffect): string {
  if (effect.kind === 'NARRATIVE_ONLY') return '';
  if (effect.kind === 'CAPABILITY_GRANT') {
    return effect.capability_value === null ? '' : `${effect.capability_value}`;
  }
  // A perk with no number reaches the wire as null, whatever the type says.
  const value = effect.scaled_value as number | null;
  if (value === null) return '';
  const signed = effect.kind === 'FLAT_BONUS' || effect.kind === 'INTENSITY_BUMP';
  return signed && value > 0 ? `+${value}` : `${value}`;
}

/**
 * How a numeric perk's amount was worked out: the authored value times the level
 * multiplier. A product that is not whole is shown with its rounding ("6 x 0.9 = 5.4,
 * rounded to 5"), so the working always reads the same as the amount beside it.
 */
export function perkWorking(effect: PreviewedEffect): string | null {
  if (effect.authored_value === null) return null;
  const times = `${effect.authored_value} x ${effect.level_multiplier}`;
  // Multipliers move in tenths; fix the float product to one place before comparing.
  const product = Number((effect.authored_value * effect.level_multiplier).toFixed(1));
  if (Number.isInteger(product) || Math.round(product) !== effect.scaled_value) return times;
  return `${times} = ${product}, rounded to ${effect.scaled_value}`;
}

/**
 * Where the thread level a perk was read at comes from. The leading resonance reads the
 * thread's full level; another resonance on the thread reads lower.
 */
export function levelReadLine(thread: Thread, option: PayerOption): string {
  const row = (thread.resonances ?? []).find((r) => r.resonance_id === option.resonance_id);
  if (row?.leads !== false) return `${option.level_read}`;
  const name = option.resonance_name;
  return `${option.level_read} (thread is ${thread.level}; ${name} is not its leading resonance)`;
}
