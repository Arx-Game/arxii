/**
 * Types shared by the guided Glimpse flow (#2427) and its two mount points —
 * the CG GiftStage (`character-creation/components/gift/GlimpseSection.tsx`)
 * and the character sheet (Task 6). This is the single definition of
 * `GlimpseTagOption` — re-export it rather than redeclaring it elsewhere.
 */

import type { ReactNode } from 'react';

/** A `DistinctionOffer` embedded on a glimpse tag row (#3675). */
export interface TagOffer {
  offer_id: number;
  distinction_id: number;
  name: string;
  player_line: string;
  cost_per_rank: number;
  max_rank: number;
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
  /** "Skip for now" — clears nothing, just collapses the flow. */
  onSkip?: () => void;
  /** Labels the deferral affordance; CG shows both buttons, sheet omits skip. */
  showDeferralControls: boolean;
  /**
   * Renders the distinction offers opened by an axis's current selection,
   * mounted after that axis's tag grid (#3675). Omitted mount points render
   * no offers section.
   */
  renderOffers?: (axis: GlimpseTagOption['axis'], selectedTagIds: number[]) => ReactNode;
  /**
   * Staff-authorable hint printed under the story textarea (#3675),
   * e.g. "The detail behind any of the picks above goes here; the picks
   * stay short." Omitted mount points render no hint.
   */
  storyHint?: string;
}
