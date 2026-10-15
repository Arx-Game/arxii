/**
 * Worship API shapes (#3779): a character's prayers and the visions sent to them.
 * Mirrors `world.worship.serializers` through the generated schema.
 */

import type { components } from '@/generated/api';

export type Prayer = components['schemas']['Prayer'];
export type Vision = components['schemas']['Vision'];
export type VisionCreate = components['schemas']['VisionCreateRequest'];

/** The Call on favor picker (#4333): the beings the character can call on, and the bonuses. */
export type InvocationOptions = components['schemas']['InvocationOptions'];
export type InvocationOption = components['schemas']['InvocationOption'];
export type InvocationBonusRow = components['schemas']['InvocationBonusRow'];

/** A Call on favor choice made in the picker, carried to the check it was made for. */
export interface InvocationChoice {
  beingId: number;
  beingName: string;
  /** The invocation check's difficulty band label ("Easy"), for "Invoking X first (Easy)". */
  bandLabel: string;
  /** The player's optional one line of how it shows; the room sees it. */
  line: string;
}
