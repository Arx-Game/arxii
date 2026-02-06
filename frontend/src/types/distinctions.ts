/**
 * TypeScript types for the distinctions system.
 *
 * These types correspond to the Django REST Framework serializers in
 * src/world/distinctions/serializers.py
 */

export interface DistinctionCategory {
  id: number;
  name: string;
  slug: string;
  description: string;
  display_order: number;
}

export interface DistinctionTag {
  id: number;
  name: string;
  slug: string;
}

export interface DistinctionEffect {
  id: number;
  target: number;
  target_name: string;
  category: string;
  value_per_rank: number | null;
  scaling_values: number[] | null;
  description: string;
  codex_entry_id?: number | null;
}

/**
 * Effect summary returned in list view (lighter weight than full DistinctionEffect).
 * Includes text and optional codex_entry_id for linkable terms.
 */
export interface EffectSummary {
  text: string;
  codex_entry_id: number | null;
}

export interface Distinction {
  id: number;
  name: string;
  slug: string;
  description: string;
  category_slug: string;
  cost_per_rank: number;
  max_rank: number;
  is_variant_parent: boolean;
  allow_other: boolean;
  tags: DistinctionTag[];
  effects_summary: EffectSummary[];
  is_locked: boolean;
  lock_reason: string | null;
}

export interface DistinctionDetail extends Omit<Distinction, 'category_slug' | 'effects_summary'> {
  category: DistinctionCategory;
  effects: DistinctionEffect[];
  variants: Distinction[];
  prerequisite_description: string | null;
}

export interface DraftDistinction {
  distinction_id: number;
  distinction_slug: string;
  rank: number;
  notes: string;
}

export interface CharacterDistinction {
  id: number;
  distinction: Distinction;
  rank: number;
  notes: string;
  origin: 'character_creation' | 'gameplay';
  is_temporary: boolean;
  total_cost: number;
  is_automatic: boolean;
}

/**
 * Response from adding a distinction to a draft.
 * Matches the _build_distinction_entry format from views.py.
 */
export interface DraftDistinctionEntry {
  distinction_id: number;
  distinction_name: string;
  distinction_slug: string;
  category_slug: string;
  rank: number;
  cost: number;
  notes: string;
}

/**
 * Request payload for adding a distinction to a draft.
 */
export interface AddDistinctionRequest {
  distinction_id: number;
  rank?: number;
  notes?: string;
}

/**
 * Request payload for swapping distinctions on a draft.
 */
export interface SwapDistinctionRequest {
  remove_id: number;
  add_id: number;
  rank?: number;
  notes?: string;
}

/**
 * Response from the swap endpoint.
 */
export interface SwapDistinctionResponse {
  removed: number;
  added: DraftDistinctionEntry;
}

/**
 * A stat adjustment returned when distinction sync triggers stat cap enforcement.
 */
export interface StatAdjustment {
  stat: string;
  old_display: number;
  new_display: number;
  reason: string;
}

/**
 * Response from the sync distinctions endpoint.
 * Includes the synced distinctions and any stat adjustments from cap enforcement.
 */
export interface SyncDistinctionsResponse {
  distinctions: DraftDistinctionEntry[];
  stat_adjustments: StatAdjustment[];
}
