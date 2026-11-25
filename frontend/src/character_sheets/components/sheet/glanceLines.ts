import type { CharacterSheetPayload } from '@/character_sheets/api';

/**
 * The plate's two short lines under the quote: who they are, then what they look like.
 *
 * Both are built from whatever the payload actually carried, so a sparse character
 * gets a shorter line rather than a line full of "TBD" — the failure the old Stats
 * block made unmissable. The in-game sheet and the waiting sheet (#5206) both read it.
 */
export function glanceLines(
  sheet: Pick<CharacterSheetPayload, 'identity' | 'appearance'> | undefined | null
): string[] {
  if (!sheet) return [];
  const { identity, appearance } = sheet;

  // The realm is deliberately NOT here. It has its own "From" row under At a glance,
  // and a Beginning already carries a place in its name ("A Caretaker of Arx"), so
  // naming the realm again reads as a stutter.
  const who = [
    identity.species?.name,
    identity.beginnings.map((row) => row.name).join(', ') || null,
    identity.family?.name,
    identity.age !== null ? `${identity.age}` : null,
  ]
    .filter(Boolean)
    .join('. ');

  const looks = [
    appearance.height_band,
    appearance.build?.name,
    ...appearance.form_traits.map((trait) => trait.value),
  ]
    .filter(Boolean)
    .join('. ');

  return [who ? `${who}.` : '', looks ? `${looks}.` : ''].filter(Boolean);
}
