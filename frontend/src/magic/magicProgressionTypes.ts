export type DiscoveryTier = 'known' | 'uncovered' | 'unknown';
export type Eligibility = 'already_have' | 'eligible' | 'locked' | null;

export interface ProgressionMilestone {
  kind: string;
  tier: DiscoveryTier;
  title: string;
  summary: string;
  eligibility: Eligibility;
  missing: string[];
  xp_cost: number | null;
  route_name: string | null;
  codex_entry_id: number | null;
}

export interface ProgressionStage {
  stage: number;
  stage_label: string;
  is_current: boolean;
  has_undiscovered: boolean;
  milestones: ProgressionMilestone[];
}

export interface MagicProgressionResponse {
  stages: ProgressionStage[];
}
