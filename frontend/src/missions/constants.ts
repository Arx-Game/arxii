/**
 * Mission Studio frontend constants.
 *
 * Keep TextChoices-style enums here (mirrors the project's CLAUDE.md
 * "TextChoices in constants.py" rule on the FE side) so pages and
 * builder components can share string-set + label tables.
 */

import type { components } from '@/generated/api';

export type GiverKind = components['schemas']['GiverKindEnum'];

export const GIVER_KINDS: ReadonlyArray<{ value: GiverKind; label: string }> = [
  { value: 'npc', label: 'NPC (Character typeclass)' },
  { value: 'environmental_detail', label: 'Environmental detail (Object)' },
  { value: 'room_trigger', label: 'Room trigger (Room typeclass)' },
];
