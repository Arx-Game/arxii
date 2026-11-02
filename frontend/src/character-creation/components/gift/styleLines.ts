/**
 * The two profile lines a fighting style shows (#4921), in the Gift stage's style step and
 * on the character sheet: how it attacks and how it defends, in the gear kinds' own labels.
 */

import type { CGCombatStyleOption } from '../../types';

/** What the two lines read: the CG style option, and the sheet's combat style too. */
export type StyleProfileFields = Pick<
  CGCombatStyleOption,
  'weapon_kinds' | 'armor_kinds' | 'hit_stat_name' | 'armor_share_tenths' | 'defense_style_display'
>;

function lower(labels: { label: string }[]): string[] {
  return labels.map((kind) => kind.label.toLowerCase());
}

function capitalized(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/** "one-handed melee, thrown · hits with Agility", or undefined with nothing to say. */
export function attacksLine(style: StyleProfileFields): string | undefined {
  const parts = [
    lower(style.weapon_kinds).join(', '),
    style.hit_stat_name ? `hits with ${capitalized(style.hit_stat_name)}` : '',
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(' · ') : undefined;
}

/** "evasion · light armor or robe, 3 of 10 counts" ("all of it counts" at 10). */
export function defendsLine(style: StyleProfileFields): string {
  const share =
    style.armor_share_tenths >= 10
      ? 'all of it counts'
      : `${style.armor_share_tenths} of 10 counts`;
  const armor = lower(style.armor_kinds).join(' or ');
  return `${style.defense_style_display.toLowerCase()} · ${armor ? `${armor}, ${share}` : share}`;
}
