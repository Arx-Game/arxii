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
/** The worn pieces that count with a being (#4520): what each means, and the ease it gives. */
export type WornMeaning = components['schemas']['WornMeaning'];
export type WornPiece = components['schemas']['WornPiece'];

/** A Call on favor choice made in the picker, carried to the check it was made for. */
export interface InvocationChoice {
  beingId: number;
  beingName: string;
  /** The invocation check's difficulty band label ("Easy"), for "Invoking X first (Easy)". */
  bandLabel: string;
  /** The player's optional one line of how it shows; the room sees it. */
  line: string;
}

/** Pledges (#4333 slice 2): a being's pledge types, what earns favor, and a character's card. */
export type Pledge = components['schemas']['Pledge'];
export type ServiceTerms = components['schemas']['ServiceTerms'];
export type PledgeCard = components['schemas']['PledgeCard'];
/** The pact a pledge offers at its close (#4341), built from the offer's rows. */
export type PactOfferSummary = components['schemas']['PactOfferSummary'];
/** A character's pact with a being as her card shows it (#4341); owner and staff only. */
export type PactCard = components['schemas']['PactCard'];
export type PledgeCreditLine = components['schemas']['PledgeCreditLine'];
/** A being holy where the acting character stands: its shrine here or the temple over it. */
export type HolySite = components['schemas']['HolySite'];

/** `PledgeCard.state`, as the server derives it (`world.worship.constants.PledgeState`). */
export const PLEDGE_STATE = {
  open: 'open',
  ready: 'ready',
  closed: 'closed',
  lapsed: 'lapsed',
} as const;

/** `PactCommitmentLine.kind` (`world.pacts.constants.CharacterPactCommitmentKind`). */
export const PACT_COMMITMENT_KIND = {
  favorEarned: 'favor_earned',
  custom: 'custom',
} as const;
