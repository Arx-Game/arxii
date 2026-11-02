/**
 * The natural weapons block on Physical (#4898): claws, a bite or horns a gift gave the
 * character, struck on Unarmed and never removable. Owner and staff only; the payload is
 * empty for anyone else, who sees the same weapon under Wearing.
 *
 * One entry per weapon, after the approved demo's "Natural weapons, a clawed character"
 * card: the name, an Unarmed tag, which gift it is from, then one line of what it does.
 */

import type { CharacterSheetNaturalWeapon } from '@/character_sheets/api';
import { Entries, Entry, Heading, Stack, Tag } from './primitives';

export function NaturalWeapons({ weapons }: { weapons: CharacterSheetNaturalWeapon[] }) {
  if (weapons.length === 0) return null;
  return (
    <Stack>
      <Heading>Natural weapons</Heading>
      <Entries>
        {weapons.map((weapon) => (
          <Entry
            key={weapon.id}
            name={weapon.name}
            tags={<Tag>Unarmed</Tag>}
            gloss={
              weapon.from_species
                ? `From the species gift ${weapon.gift_name}.`
                : `From the gift ${weapon.gift_name}.`
            }
          >
            <p className="refsheet-note">{weaponLine(weapon)}</p>
          </Entry>
        ))}
      </Entries>
    </Stack>
  );
}

/** "5 slashing damage · Keenness, 1 of 1 · cannot be taken from you". */
function weaponLine(weapon: CharacterSheetNaturalWeapon): string {
  const damage = weapon.damage_type
    ? `${weapon.damage} ${weapon.damage_type.toLowerCase()} damage`
    : `${weapon.damage} damage`;
  const parts = [damage];
  if (weapon.facets.length > 0) {
    const names = weapon.facets.join(', ');
    parts.push(
      weapon.facet_capacity > 0
        ? `${names}, ${weapon.facets_used} of ${weapon.facet_capacity}`
        : names
    );
  }
  parts.push('cannot be taken from you');
  return parts.join(' · ');
}
