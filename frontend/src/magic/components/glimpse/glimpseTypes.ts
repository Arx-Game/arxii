/**
 * Types shared by the guided Glimpse flow (#2427) and its two mount points —
 * the CG GiftStage (`character-creation/components/gift/GlimpseSection.tsx`)
 * and the character sheet (Task 6). This is the single definition of
 * `GlimpseTagOption` — re-export it rather than redeclaring it elsewhere.
 */

/**
 * How much of the Glimpse the character remembers (#5292). The server's
 * `GlimpseMemory` choices: a draft holds any of the four; a character holds
 * the first three, a Glimpse left for later being stored as remembered.
 */
export type GlimpseMemory = 'remembered' | 'blacked_out' | 'no_memory' | 'later';

/**
 * The card an answer gives, embedded on its glimpse tag row (#3675, #5292). It comes
 * free with the answer, so the price fields say what the card is and are never
 * charged; `effect_line` is its mechanics line ("+Anima"), blank for a card with none.
 */
export interface TagOffer {
  offer_id: number;
  distinction_id: number;
  name: string;
  player_line: string;
  cost_per_rank: number;
  max_rank: number;
  effect_line: string;
}

/**
 * One part of the Glimpse as both mounts ask it: its axis and how it behaves.
 * `givesCard` and `lostInBlackout` copy `GLIMPSE_AXIS_CONFIG` in
 * `world.magic.constants`, the authoritative source this must not drift from.
 */
export interface GlimpseAxisStep {
  axis: GlimpseTagOption['axis'];
  /** The question the sheet's editor heads the part with. */
  label: string;
  /** Takes several answers. No part does since #5292; the path stays as the way back. */
  multi: boolean;
  /** An answer of this part may carry a card. */
  givesCard: boolean;
  /** A character who blacked out has no answer to this part. */
  lostInBlackout: boolean;
}

/**
 * Glimpse tag catalog row.
 * From GET /api/character-creation/glimpse-tags/
 */
export interface GlimpseTagOption {
  id: number;
  axis: 'TONE' | 'CONSEQUENCE' | 'WITNESS' | 'SENSORY' | 'TRIGGER' | 'CHOOSING' | 'REFLECTION';
  name: string;
  slug: string;
  description: string;
  example: string;
  sort_order: number;
  /**
   * This tag cannot be picked with any other tag of its axis (#5193); the
   * rule lives in `axisSelection.ts`'s `nextAxisSelection`.
   */
  stands_alone: boolean;
  offers: TagOffer[];
}

export interface GlimpseFlowProps {
  /**
   * Staff-authorable section heading, rendered at the top of the flow above
   * the axis accordion. Defaults to `'The Glimpse'`. Mirrors the
   * `magic_glimpse_heading` CGExplanation row the way the sibling Motif
   * field uses `magic_motif_heading` — threaded in by whichever mount point
   * (GiftStage/GlimpseSection today) has access to the copy query.
   */
  heading?: string;
  /** Full active catalog. */
  tags: GlimpseTagOption[];
  selectedTagIds: number[];
  prose: string;
  /** Replace the selection for one axis (already arity-enforced by the UI). */
  onChangeAxis: (axis: GlimpseTagOption['axis'], tagIds: number[]) => void;
  onChangeProse: (text: string) => void;
  /**
   * Parts whose saved answer cannot be changed here (#5292): an answer written in
   * play is final for the player. A closed part shows its answers and takes no click.
   */
  closedAxes?: ReadonlySet<GlimpseTagOption['axis']>;
  /** Parts not asked at all (#5292): the two a blackout took. */
  hiddenAxes?: ReadonlySet<GlimpseTagOption['axis']>;
  /**
   * Staff-authorable hint printed under the story textarea (#3675),
   * e.g. "The detail behind any of the picks above goes here; the picks
   * stay short." Omitted mount points render no hint.
   */
  storyHint?: string;
}
