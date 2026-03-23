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

export interface ActionResultData {
  interaction_id: number;
  action_key: string | null;
  check_result: CheckResultData | null;
  technique_name: string | null;
  selected_consequence: ConsequenceData | null;
  applied_effects: AppliedEffectData[];
}

export interface ActionRequestResponse {
  status: 'pending' | 'resolved';
  request_id?: number;
  result?: ActionResultData;
}

export interface Place {
  id: number;
  name: string;
  description: string;
}
