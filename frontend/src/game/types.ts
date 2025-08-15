export interface ParamSchema {
  type: string;
  required?: boolean;
  match?: string;
}

export interface CommandSpec {
  action: string;
  prompt: string;
  params_schema: Record<string, ParamSchema>;
  icon: string;
}
