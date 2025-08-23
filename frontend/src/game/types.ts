export interface ParamSchema {
  type: string;
  required?: boolean;
  match?: string;
  widget?: string;
  options_endpoint?: string;
}

export interface CommandSpec {
  action: string;
  prompt: string;
  params_schema: Record<string, ParamSchema>;
  icon: string;
  /** Human readable command name. */
  name?: string;
  /** Category used for grouping commands. */
  category?: string;
  /** Help text describing command usage. */
  help?: string;
}
