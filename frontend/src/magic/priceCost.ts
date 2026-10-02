/**
 * A price's real cost as short display parts (#4099): what each paid cast
 * consumes and the condition it inflicts. The item and condition names are
 * authored rows; "Consumes" / "Inflicts" are interface chrome. Shared by the
 * CG price picker and the Spellbook so both say it the same way.
 */
import type { TechniquePriceComponent } from './types';

export function priceCostParts(
  consumes: TechniquePriceComponent[],
  inflicts: string | null
): string[] {
  const parts: string[] = [];
  if (consumes.length > 0) {
    parts.push(`Consumes ${consumes.map((c) => `${c.quantity}× ${c.name}`).join(', ')}`);
  }
  if (inflicts) parts.push(`Inflicts ${inflicts}`);
  return parts;
}
