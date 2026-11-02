/**
 * The fighting style block beside the Gift (#4921): how the character was taught to fight
 * with magic. Owner and staff only; the payload is null for anyone else and for a
 * character with no style.
 *
 * One entry, the shape the Gift stage's style step draws: the name, the defense style as
 * its tag, the description, the Attacks and Defends lines, then the style skill's value.
 */

import type { CharacterSheetCombatStyle } from '@/character_sheets/api';
import { attacksLine, defendsLine } from '@/character-creation/components/gift/styleLines';
import { Entries, Entry, Heading, Stack, Tag } from './primitives';

export function FightingStyle({ style }: { style: CharacterSheetCombatStyle | null }) {
  if (!style) return null;
  const attacks = attacksLine(style);
  return (
    <Stack>
      <Heading>Fighting style</Heading>
      <Entries>
        <Entry
          name={style.name}
          tags={<Tag>{style.defense_style_display}</Tag>}
          gloss={style.description || undefined}
        >
          {attacks && <p className="refsheet-note">Attacks: {attacks}</p>}
          <p className="refsheet-note">Defends: {defendsLine(style)}</p>
          {style.skill_name && (
            <p className="refsheet-note">
              {style.skill_name} {style.skill_value}
            </p>
          )}
        </Entry>
      </Entries>
    </Stack>
  );
}
