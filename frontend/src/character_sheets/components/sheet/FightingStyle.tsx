/**
 * The fighting style block beside the Gift (#4921): how the character was taught to fight
 * with magic. Owner and staff only; the payload is null for anyone else and for a
 * character with no style.
 *
 * After the approved demo's screen 6 style card: the style's name with its defense style
 * as a tag and its description, then Tradition, Attacks, Defends and Vows rows (a row with
 * nothing to say is dropped), then the style skill's value. Creation never shows the vows;
 * the sheet does.
 */

import type { CharacterSheetCombatStyle } from '@/character_sheets/api';
import { attacksLine, defendsLine } from '@/character-creation/components/gift/styleLines';
import { Entries, Entry, Glance, Heading, Stack, Tag } from './primitives';

export function FightingStyle({ style }: { style: CharacterSheetCombatStyle | null }) {
  if (!style) return null;
  return (
    <Stack>
      <Heading>Fighting style</Heading>
      <Entries>
        <Entry
          name={style.name}
          tags={<Tag>{style.defense_style_display}</Tag>}
          gloss={style.description || undefined}
        >
          <Glance
            rows={[
              { label: 'Tradition', value: style.tradition_name },
              { label: 'Attacks', value: attacksLine(style) },
              { label: 'Defends', value: defendsLine(style) },
              { label: 'Vows', value: style.vows.join(', ') },
              {
                label: style.skill_name,
                value: style.skill_name ? String(style.skill_value) : '',
              },
            ]}
          />
        </Entry>
      </Entries>
    </Stack>
  );
}
