/**
 * Flows Builder shared types (#3417 task 9).
 *
 * Hand-written against the flows authoring API (`flows.views` /
 * `flows.serializers` / `flows.catalog`), not generated — the catalog shape
 * is dataclass-driven rather than OpenAPI-schema-driven. Keep these in sync
 * with the backend shapes documented in `docs/systems/flows.md` if that
 * doc exists, or with the serializers directly (`src/flows/serializers.py`,
 * `src/flows/catalog.py`) otherwise.
 */

/** Paginated list shape DRF returns. */
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ---------------------------------------------------------------------------
// DSL authoring catalog (GET /api/flows/catalog/)
// ---------------------------------------------------------------------------

export type ParamType = 'str' | 'int' | 'float' | 'bool' | 'json' | 'dict';

export interface ParamSpec {
  name: string;
  type: ParamType;
  required: boolean;
  description: string;
  accepts_reference: boolean;
  choices: string[];
}

export interface StepActionSpec {
  action: string;
  label: string;
  description: string;
  variable_name_role: string;
  variable_name_required: boolean;
  params: ParamSpec[];
  is_conditional: boolean;
  allows_extra_params: boolean;
}

export interface EventCatalogEntry {
  name: string;
  label: string;
  payload_fields: { name: string; type: string }[] | null;
}

export interface ServiceFunctionEntry {
  name: string;
  description: string;
  params: { name: string; type: string }[];
}

export interface DslCatalog {
  actions: StepActionSpec[];
  events: EventCatalogEntry[];
  service_functions: ServiceFunctionEntry[];
  filter_ops: string[];
  variable_name_roles: string[];
}

// ---------------------------------------------------------------------------
// FlowDefinition / FlowStepDefinition
// ---------------------------------------------------------------------------

/** One saved step, as returned by the flow detail endpoint. */
export interface FlowStep {
  id: number;
  parent: number | null;
  action: string;
  variable_name: string;
  parameters: Record<string, unknown>;
}

/**
 * One authored step in the client-side tree, addressed by an author-chosen
 * `clientId` rather than a DB pk — the tree may mix brand-new steps with a
 * rename of existing ones before the whole tree is saved in one PUT/PATCH.
 */
export interface ClientStep {
  clientId: string;
  parentClientId: string | null;
  action: string;
  variableName: string;
  parameters: Record<string, unknown>;
}

export interface FlowSummary {
  id: number;
  name: string;
  description: string | null;
  step_count: number;
}

export interface FlowInteractions {
  run_by: {
    id: number;
    name: string;
    event_name: string;
    installing_templates: { id: number; name: string }[];
  }[];
  emits: { event_name: string; listeners: { id: number; name: string }[] }[];
  calls: string[];
}

export interface FlowDetail extends FlowSummary {
  steps: FlowStep[];
  interactions: FlowInteractions;
}

/**
 * Create/update payload. `steps` omitted means "leave the existing steps
 * untouched" (update only); `steps: []` or a populated list replaces the
 * entire tree.
 */
export interface FlowWritePayload {
  name: string;
  description?: string;
  steps?: ClientStep[];
}

/**
 * The write endpoints' response shape — `FlowDefinitionWriteSerializer`
 * declares `steps` write_only and has no `step_count` field, so POST/PUT/PATCH
 * responses are narrower than `FlowSummary`. Callers must re-GET the detail
 * endpoint to see the saved step tree.
 */
export interface FlowWriteResult {
  id: number;
  name: string;
  description: string | null;
}

// ---------------------------------------------------------------------------
// TriggerDefinition / Trigger
// ---------------------------------------------------------------------------

export interface TriggerDefinition {
  id: number;
  name: string;
  event_name: string;
  flow_definition: number;
  base_filter_condition: unknown | null;
  description: string | null;
  priority: number;
}

export type TriggerDefinitionWritePayload = Partial<Omit<TriggerDefinition, 'id'>>;

export interface TriggerRow {
  id: number;
  trigger_definition: number;
  obj: number;
  additional_filter_condition: unknown | null;
  source_condition: number | null;
  source_stage: number | null;
}

export type TriggerWritePayload = Partial<Omit<TriggerRow, 'id'>>;
