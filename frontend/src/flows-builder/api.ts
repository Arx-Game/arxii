/**
 * Flows Builder API fetch wrappers (#3417 task 9).
 *
 * Pure functions — pair with React Query hooks in queries.ts. Use the
 * shared `apiFetch` for cookie/CSRF and base-URL handling. Every endpoint
 * here is staff/GM-only (`IsGMOrStaff` read, `IsAdminUser` write on the
 * backend), matching `flows.views` — except the conditions templates
 * endpoint this module also reads, which is `IsAuthenticated` (player-facing
 * for TechniqueBuilderPage); its `reactive_trigger_ids` field is gated
 * server-side to staff/GM requesters instead (#3417 leak analysis).
 */

import { apiFetch } from '@/evennia_replacements/api';

import type {
  ClientStep,
  DslCatalog,
  FlowDetail,
  FlowSummary,
  FlowWritePayload,
  FlowWriteResult,
  PaginatedResponse,
  TriggerDefinition,
  TriggerDefinitionWritePayload,
  TriggerRow,
  TriggerWritePayload,
} from './types';

const BASE_URL = '/api/flows';
const CONDITIONS_BASE_URL = '/api/conditions';

/**
 * Mirrors `missions/api.ts`'s `ApiValidationError` — kept as a local copy
 * rather than a cross-feature import from `missions/api.ts`. There is no
 * eslint import-boundary rule blocking that import today, but a local copy
 * keeps flows-builder independent of the missions module's internals (and
 * of any future boundary rule) for what is a two-field error wrapper.
 */
export class ApiValidationError extends Error {
  readonly fieldErrors: Record<string, unknown>;
  constructor(detail: unknown) {
    super('Validation error');
    this.name = 'ApiValidationError';
    this.fieldErrors =
      typeof detail === 'object' && detail !== null ? (detail as Record<string, unknown>) : {};
  }
}

function buildQueryString(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.append(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : '';
}

/**
 * Client-step -> wire-shape mapping. Exported so `stepTree.ts`'s
 * `toWirePayload` can reuse it instead of duplicating the field-name
 * mapping (`stepTree.ts` operates on a bare `ClientStep[]`, not a full
 * `FlowWritePayload`, so it calls this directly rather than
 * `toApiFlowPayload`).
 */
export function toApiStep(step: ClientStep): Record<string, unknown> {
  return {
    client_id: step.clientId,
    parent_client_id: step.parentClientId,
    action: step.action,
    variable_name: step.variableName,
    parameters: step.parameters,
  };
}

function toApiFlowPayload(payload: FlowWritePayload): Record<string, unknown> {
  const body: Record<string, unknown> = {
    name: payload.name,
    description: payload.description,
  };
  if (payload.steps !== undefined) {
    body.steps = payload.steps.map(toApiStep);
  }
  return body;
}

async function throwValidationError(res: Response): Promise<never> {
  const detail = await res.json().catch(() => ({}));
  throw new ApiValidationError(detail);
}

// ---------------------------------------------------------------------------
// DSL authoring catalog
// ---------------------------------------------------------------------------

export async function fetchDslCatalog(): Promise<DslCatalog> {
  const res = await apiFetch(`${BASE_URL}/catalog/`);
  if (!res.ok) throw new Error('Failed to load the flows DSL catalog');
  return res.json();
}

// ---------------------------------------------------------------------------
// FlowDefinition
// ---------------------------------------------------------------------------

export async function listFlows(search?: string): Promise<PaginatedResponse<FlowSummary>> {
  const res = await apiFetch(`${BASE_URL}/flows/${buildQueryString({ search })}`);
  if (!res.ok) throw new Error('Failed to load flows');
  return res.json();
}

export async function getFlow(id: number): Promise<FlowDetail> {
  const res = await apiFetch(`${BASE_URL}/flows/${id}/`);
  if (!res.ok) throw new Error(`Failed to load flow ${id}`);
  return res.json();
}

export async function createFlow(payload: FlowWritePayload): Promise<FlowWriteResult> {
  const res = await apiFetch(`${BASE_URL}/flows/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toApiFlowPayload(payload)),
  });
  if (!res.ok) return throwValidationError(res);
  return res.json();
}

export async function updateFlow(id: number, payload: FlowWritePayload): Promise<FlowWriteResult> {
  const res = await apiFetch(`${BASE_URL}/flows/${id}/`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toApiFlowPayload(payload)),
  });
  if (!res.ok) return throwValidationError(res);
  return res.json();
}

export async function deleteFlow(id: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/flows/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete flow ${id}`);
}

// ---------------------------------------------------------------------------
// TriggerDefinition
// ---------------------------------------------------------------------------

export async function listTriggerDefinitions(
  filters: { event_name?: string; search?: string; page?: number; page_size?: number } = {}
): Promise<PaginatedResponse<TriggerDefinition>> {
  const res = await apiFetch(`${BASE_URL}/trigger-definitions/${buildQueryString(filters)}`);
  if (!res.ok) throw new Error('Failed to load trigger definitions');
  return res.json();
}

export async function getTriggerDefinition(id: number): Promise<TriggerDefinition> {
  const res = await apiFetch(`${BASE_URL}/trigger-definitions/${id}/`);
  if (!res.ok) throw new Error(`Failed to load trigger definition ${id}`);
  return res.json();
}

export async function createTriggerDefinition(
  payload: TriggerDefinitionWritePayload
): Promise<TriggerDefinition> {
  const res = await apiFetch(`${BASE_URL}/trigger-definitions/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) return throwValidationError(res);
  return res.json();
}

export async function updateTriggerDefinition(
  id: number,
  payload: TriggerDefinitionWritePayload
): Promise<TriggerDefinition> {
  const res = await apiFetch(`${BASE_URL}/trigger-definitions/${id}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) return throwValidationError(res);
  return res.json();
}

export async function deleteTriggerDefinition(id: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/trigger-definitions/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete trigger definition ${id}`);
}

// ---------------------------------------------------------------------------
// Trigger (a TriggerDefinition installed on a specific object)
// ---------------------------------------------------------------------------

export async function listTriggers(
  filters: {
    trigger_definition?: number;
    obj?: number;
    search?: string;
    page?: number;
    page_size?: number;
  } = {}
): Promise<PaginatedResponse<TriggerRow>> {
  const res = await apiFetch(`${BASE_URL}/triggers/${buildQueryString(filters)}`);
  if (!res.ok) throw new Error('Failed to load triggers');
  return res.json();
}

export async function getTrigger(id: number): Promise<TriggerRow> {
  const res = await apiFetch(`${BASE_URL}/triggers/${id}/`);
  if (!res.ok) throw new Error(`Failed to load trigger ${id}`);
  return res.json();
}

export async function createTrigger(payload: TriggerWritePayload): Promise<TriggerRow> {
  const res = await apiFetch(`${BASE_URL}/triggers/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) return throwValidationError(res);
  return res.json();
}

export async function updateTrigger(id: number, payload: TriggerWritePayload): Promise<TriggerRow> {
  const res = await apiFetch(`${BASE_URL}/triggers/${id}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) return throwValidationError(res);
  return res.json();
}

export async function deleteTrigger(id: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/triggers/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete trigger ${id}`);
}

// ---------------------------------------------------------------------------
// ConditionTemplate reactive-trigger wiring (world.conditions, not flows)
// ---------------------------------------------------------------------------

/**
 * Minimal summary of a `ConditionTemplate` for the condition-wiring picker
 * (#3417 task 12). No existing frontend fetcher covers
 * `/api/conditions/templates/` — `conditions/api.ts` only has
 * instance/damage-type/treatment fetchers — so this is added here rather
 * than there, next to the `setReactiveTriggers` call it exists to support.
 * `reactive_trigger_ids` is the read-only exposure of the
 * `ConditionTemplate.reactive_triggers` M2M (`ConditionTemplateSerializer`,
 * `src/world/conditions/serializers.py`) added alongside this task: the
 * wiring UI needs a template's CURRENT full set before calling
 * `setReactiveTriggers`, since that endpoint replaces the whole set rather
 * than adding/removing one id.
 */
export interface ConditionTemplateSummary {
  id: number;
  name: string;
  reactive_trigger_ids: number[];
}

/**
 * List every condition template (staff/GM picker data).
 * GET /api/conditions/templates/ — UNPAGINATED (`pagination_class = None`
 * on `ConditionTemplateViewSet`), so this returns a plain array.
 */
export async function listConditionTemplates(): Promise<ConditionTemplateSummary[]> {
  const res = await apiFetch(`${CONDITIONS_BASE_URL}/templates/`);
  if (!res.ok) throw new Error('Failed to load condition templates');
  return res.json();
}

/**
 * Replace the complete set of TriggerDefinitions a ConditionTemplate installs
 * when it applies (`.set()` semantics — this is not additive).
 */
export async function setReactiveTriggers(
  templateId: number,
  triggerDefinitionIds: number[]
): Promise<{ trigger_definition_ids: number[] }> {
  const res = await apiFetch(
    `${CONDITIONS_BASE_URL}/templates/${templateId}/set_reactive_triggers/`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trigger_definition_ids: triggerDefinitionIds }),
    }
  );
  if (!res.ok) return throwValidationError(res);
  return res.json();
}
