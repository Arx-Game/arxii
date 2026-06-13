/**
 * Currency display helpers.
 *
 * All backend money is integer coppers (the single base unit). The canonical
 * display rule is the mixed form — "3g 4s 7c" — and the system always does
 * the arithmetic: players never see raw copper totals they have to convert.
 * Ladder: 10c = 1s, 100c = 1g. Named instruments above gold (Gold Knight,
 * Baroness, ...) are physical items, not display units; ledgers read in gold.
 */

const COPPERS_PER_SILVER = 10;
const COPPERS_PER_GOLD = 100;

/** Format integer coppers as the canonical mixed form, e.g. "3g 4s 7c". */
export function formatCoppers(coppers: number): string {
  if (!Number.isFinite(coppers)) return '0c';
  // Derive the sign from the truncated value so a fractional amount in (-1, 0)
  // doesn't leave a lone minus on a zero magnitude ("-0c").
  const whole = Math.trunc(coppers);
  const negative = whole < 0;
  const total = Math.abs(whole);

  const gold = Math.floor(total / COPPERS_PER_GOLD);
  const silver = Math.floor((total % COPPERS_PER_GOLD) / COPPERS_PER_SILVER);
  const copper = total % COPPERS_PER_SILVER;

  const parts: string[] = [];
  if (gold > 0) parts.push(`${gold.toLocaleString('en-US')}g`);
  if (silver > 0) parts.push(`${silver}s`);
  if (copper > 0 || parts.length === 0) parts.push(`${copper}c`);

  return `${negative ? '-' : ''}${parts.join(' ')}`;
}
