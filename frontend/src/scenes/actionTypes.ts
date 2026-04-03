export interface TechniqueOption {
  id: number;
  name: string;
  capability_type: string;
  capability_value: number;
}

export interface AvailableAction {
  key: string;
  name: string;
  icon: string;
  category: string;
  techniques: TechniqueOption[];
  applicable_techniques?: TechniqueOption[];
}

export interface TechniqueAction {
  template_id: number;
  name: string;
  icon: string;
  category: string;
  target_type: string;
  technique_id: number;
  technique_name: string;
}

export interface AvailableActionsResponse {
  self_actions: AvailableAction[];
  targeted_actions: AvailableAction[];
  technique_actions: TechniqueAction[];
}

export interface SoulfrayWarningData {
  stage_name: string;
  stage_description: string;
  has_death_risk: boolean;
}

export interface AvailableEnhancement {
  technique_id: number;
  technique_name: string;
  variant_name: string;
  effective_cost: number;
  soulfray_warning: SoulfrayWarningData | null;
}

export interface AvailableSceneAction {
  action_key: string;
  action_template_name: string;
  icon: string;
  enhancements: AvailableEnhancement[];
}

export interface ActionRequest {
  id: number;
  initiator_persona: { id: number; name: string };
  action_name: string;
  technique_name: string | null;
  created_at: string;
}

export interface CheckResultData {
  outcome: string;
  success_level: number;
}

export interface ConsequenceData {
  label: string;
  outcome_tier: string;
}

export interface AppliedEffectData {
  type: string;
  condition?: string;
  duration?: string;
}

export interface TechniqueResultData {
  confirmed: boolean;
  anima_spent: number;
  soulfray_stage: string | null;
  mishap_label: string | null;
}

export interface ActionResolutionStepData {
  step_label: string;
  check_outcome: string;
  consequence_id: number | null;
}

export interface ActionResolutionData {
  current_phase: string;
  main_result: ActionResolutionStepData | null;
  gate_results: ActionResolutionStepData[];
}

export interface ActionResultData {
  interaction_id: number;
  action_key: string | null;
  action_resolution: ActionResolutionData;
  technique_result: TechniqueResultData | null;
  technique_name: string | null;
  /** @deprecated Use action_resolution.main_result instead */
  check_result: CheckResultData | null;
  /** @deprecated Use technique_name instead */
  selected_consequence: ConsequenceData | null;
  applied_effects: AppliedEffectData[];
}

export interface ActionRequestResponse {
  status: 'pending' | 'resolved';
  request_id?: number;
  result?: ActionResultData;
}

export interface ActionAttachmentInfo {
  actionKey: string;
  name: string;
  target?: string;
  requiresTarget: boolean;
  techniqueId?: number;
  targetPersonaId?: number;
}

export interface Place {
  id: number;
  name: string;
  description: string;
}
