export interface ConsequenceDisplay {
  label: string;
  tier_name: string;
  weight: number;
  is_selected: boolean;
}

export interface RoulettePayload {
  template_name: string;
  consequences: ConsequenceDisplay[];
}
