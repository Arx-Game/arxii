/**
 * Mission Studio shared types — thin aliases over the generated OpenAPI
 * schema. The generated types are the source of truth (regenerated via
 * `just gen-api-types`); local aliases give us short, ergonomic names.
 *
 * NOTE: MissionTemplate and MissionTemplateDetail are defined as explicit
 * interfaces here (not aliases of the generated schema) because the backend
 * has dropped the `slug` field and changed `categories` to id-based
 * (number[]).  The generated api.d.ts will be regenerated in a later step;
 * until then these local types are the source of truth for the frontend.
 */

import type { components } from '@/generated/api';

export interface MissionTemplate {
  readonly id: number;
  name: string;
  /** Rich IC opening lore (mission bookend). */
  summary: string;
  /** Rich IC wrap-up lore. */
  epilogue?: string;
  level_band_min: number;
  level_band_max: number;
  risk_tier: number;
  /** Relative weight in the availability draw. */
  base_weight?: number;
  /** Arc association — the era this mission was authored for. */
  created_in_era?: number | null;
  arc_scope: components['schemas']['ArcScopeEnum'];
  /** Percent chance this template replaces an existing offer (0-100). */
  percent_replace?: number;
  /** Per-giver re-offer cooldown. */
  cooldown: string;
  reward_group_rule?: components['schemas']['RewardGroupRuleEnum'];
  is_active?: boolean;
  access_tier?: components['schemas']['AccessTierEnum'];
  readonly categories: readonly number[];
  /** Phase 0 predicate tree gating front-door availability for this template. */
  availability_rule?: unknown;
}

export interface MissionTemplateDetail extends MissionTemplate {
  readonly lifetime_completions: number;
  readonly active_instances: Record<string, unknown>[];
}

export interface MissionCategory {
  id: number;
  name: string;
  description: string;
  display_order: number;
}

export type MissionNode = components['schemas']['MissionNode'];
export type MissionOption = components['schemas']['MissionOption'];
export type MissionOptionRoute = components['schemas']['MissionOptionRoute'];
export type MissionOptionRouteCandidate = components['schemas']['MissionOptionRouteCandidate'];
export type MissionOptionRouteReward = components['schemas']['MissionOptionRouteReward'];
export type MissionGiver = components['schemas']['MissionGiver'];
export type MissionGiverOffering = components['schemas']['MissionGiverOffering'];
export type MissionGiverStanding = components['schemas']['MissionGiverStanding'];
export type MissionInstance = components['schemas']['MissionInstance'];

export type AccessTier = components['schemas']['AccessTierEnum'];
export type ArcScope = components['schemas']['ArcScopeEnum'];
export type GiverKind = components['schemas']['GiverKindEnum'];

/** Filter knobs for the browser page. Subset of D1's MissionTemplateFilterSet. */
export interface MissionTemplateFilters {
  name?: string;
  risk_tier?: number;
  is_active?: boolean;
  arc_scope?: ArcScope;
  access_tier?: AccessTier;
  category?: string;
  org?: string;
  level_band_contains?: number;
}

/** Paginated list shape DRF returns. */
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** The active-instance row shape inside MissionTemplateDetail. */
export interface ActiveInstanceSummary {
  instance_id: number;
  current_node_key: string | null;
  contract_holder: string | null;
}
