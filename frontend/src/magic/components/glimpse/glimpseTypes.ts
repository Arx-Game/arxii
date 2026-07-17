/**
 * Types shared by the guided Glimpse flow (#2427) and its two mount points —
 * the CG GiftStage (`character-creation/components/gift/GlimpseSection.tsx`)
 * and the character sheet (Task 6). This is the single definition of
 * `GlimpseTagOption` — re-export it rather than redeclaring it elsewhere.
 */

/** Distinction stub embedded in a glimpse tag's suggestion list. */
export interface GlimpseSuggestedDistinction {
  id: number;
  name: string;
}

/**
 * Glimpse tag catalog row.
 * From GET /api/character-creation/glimpse-tags/
 */
export interface GlimpseTagOption {
  id: number;
  axis: 'TONE' | 'CONSEQUENCE' | 'WITNESS' | 'SENSORY';
  name: string;
  slug: string;
  description: string;
  example: string;
  sort_order: number;
  suggested_distinctions: GlimpseSuggestedDistinction[];
}

export interface GlimpseFlowProps {
  /** Full active catalog. */
  tags: GlimpseTagOption[];
  selectedTagIds: number[];
  prose: string;
  linkedDistinctionIds: number[];
  /** Replace the selection for one axis (already arity-enforced by the UI). */
  onChangeAxis: (axis: GlimpseTagOption['axis'], tagIds: number[]) => void;
  onChangeProse: (text: string) => void;
  onToggleDistinctionLink: (distinctionId: number) => void;
  /** "Skip for now" — clears nothing, just collapses the flow. */
  onSkip?: () => void;
  /** Labels the deferral affordance; CG shows both buttons, sheet omits skip. */
  showDeferralControls: boolean;
  /** Distinctions available for the manual-link fallback control. */
  linkableDistinctions: GlimpseSuggestedDistinction[];
}
