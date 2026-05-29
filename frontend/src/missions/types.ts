/**
 * Mission Studio shared types — thin aliases over the generated OpenAPI
 * schema. The generated types are the source of truth (regenerated via
 * `just gen-api-types`); local aliases give us short, ergonomic names.
 */

import type { components } from '@/generated/api';

export type MissionTemplate = components['schemas']['MissionTemplate'];
export type MissionTemplateDetail = components['schemas']['MissionTemplateDetail'];

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
