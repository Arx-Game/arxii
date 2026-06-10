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
export type MissionInstance = components['schemas']['MissionInstance'];
export type MissionGiver = components['schemas']['MissionGiver'];
export type MissionGiverRequest = components['schemas']['MissionGiverRequest'];

export type MissionVisibility = components['schemas']['MissionVisibilityEnum'];

// #885 player journal/beat surface.
export type JournalEntry = components['schemas']['JournalEntry'];
export type BeatView = components['schemas']['BeatView'];
export type BeatOption = components['schemas']['BeatOption'];
export type ResolvedBeat = components['schemas']['ResolvedBeat'];
export type ArcScope = components['schemas']['ArcScopeEnum'];

/** Filter knobs for the browser page. Subset of D1's MissionTemplateFilterSet. */
export interface MissionTemplateFilters {
  name?: string;
  risk_tier?: number;
  is_active?: boolean;
  arc_scope?: ArcScope;
  visibility?: MissionVisibility;
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
