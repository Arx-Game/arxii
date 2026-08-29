/**
 * Pure tree ops / coercion / validation for the FlowStepTree editor
 * (#3417 task 10).
 *
 * `ClientStep[]` is a flat list addressed by `clientId`/`parentClientId`
 * rather than a nested structure — every op here reads/writes that flat
 * shape so the editor components never have to re-flatten a tree to save
 * it. `validateSteps` mirrors `src/flows/step_validation.py`'s
 * `validate_step_tree` rules 1-9 so an authored tree that passes here also
 * passes the server-side validation on save; keep the two in sync when
 * either changes.
 */
import { toApiStep } from './api';
import type { ClientStep, FlowStep, ParamSpec, ParamType, StepActionSpec } from './types';

// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------

export function newClientId(): string {
  return crypto.randomUUID();
}

// ---------------------------------------------------------------------------
// Tree navigation
// ---------------------------------------------------------------------------

/** Direct children of `parentId` (or the root steps, for `parentId: null`), in list order. */
export function childrenOf(steps: ClientStep[], parentId: string | null): ClientStep[] {
  return steps.filter((step) => step.parentClientId === parentId);
}

function descendantIds(steps: ClientStep[], clientId: string): Set<string> {
  const ids = new Set<string>([clientId]);
  const collect = (id: string) => {
    for (const child of childrenOf(steps, id)) {
      if (!ids.has(child.clientId)) {
        ids.add(child.clientId);
        collect(child.clientId);
      }
    }
  };
  collect(clientId);
  return ids;
}

// ---------------------------------------------------------------------------
// Mutations (all pure — return a new array, never mutate the input)
// ---------------------------------------------------------------------------

const DEFAULT_PARAM_VALUE: Record<ParamType, unknown> = {
  str: '',
  int: 0,
  float: 0,
  bool: false,
  dict: {},
  json: '',
};

function defaultParameters(params: ParamSpec[]): Record<string, unknown> {
  const parameters: Record<string, unknown> = {};
  for (const param of params) {
    parameters[param.name] = DEFAULT_PARAM_VALUE[param.type];
  }
  return parameters;
}

/** Append a new step under `parentId`, with `parameters` prefilled from the spec's defaults. */
export function addStep(
  steps: ClientStep[],
  parentId: string | null,
  action: string,
  spec: StepActionSpec
): ClientStep[] {
  const step: ClientStep = {
    clientId: newClientId(),
    parentClientId: parentId,
    action,
    variableName: '',
    parameters: defaultParameters(spec.params),
  };
  return [...steps, step];
}

/** Remove `clientId` and every step descending from it. */
export function removeStep(steps: ClientStep[], clientId: string): ClientStep[] {
  const toRemove = descendantIds(steps, clientId);
  return steps.filter((step) => !toRemove.has(step.clientId));
}

/**
 * Swap `clientId` with its previous ('up') or next ('down') sibling —
 * siblings share `parentClientId`. A no-op at either end of the sibling
 * list, or if `clientId` isn't found. Reordering never crosses parents:
 * only the two swapped steps' positions in the flat array change.
 */
export function moveStep(
  steps: ClientStep[],
  clientId: string,
  direction: 'up' | 'down'
): ClientStep[] {
  const stepIndex = steps.findIndex((step) => step.clientId === clientId);
  if (stepIndex === -1) return steps;
  const target = steps[stepIndex];
  const siblings = childrenOf(steps, target.parentClientId);
  const siblingIndex = siblings.findIndex((step) => step.clientId === clientId);
  const targetSiblingIndex = direction === 'up' ? siblingIndex - 1 : siblingIndex + 1;
  if (targetSiblingIndex < 0 || targetSiblingIndex >= siblings.length) return steps;
  const swapClientId = siblings[targetSiblingIndex].clientId;
  const swapIndex = steps.findIndex((step) => step.clientId === swapClientId);
  const next = [...steps];
  [next[stepIndex], next[swapIndex]] = [next[swapIndex], next[stepIndex]];
  return next;
}

// ---------------------------------------------------------------------------
// Coercion
// ---------------------------------------------------------------------------

function coerceParamValue(raw: unknown, paramSpec: ParamSpec): unknown {
  if (paramSpec.accepts_reference && typeof raw === 'string' && raw.startsWith('@')) {
    return raw;
  }
  if (typeof raw !== 'string') return raw;
  switch (paramSpec.type) {
    case 'int': {
      const n = parseInt(raw, 10);
      return Number.isNaN(n) ? raw : n;
    }
    case 'float': {
      const n = parseFloat(raw);
      return Number.isNaN(n) ? raw : n;
    }
    case 'bool':
      return raw === 'true' || raw === '1';
    case 'dict':
    case 'json':
      try {
        return JSON.parse(raw);
      } catch {
        return raw;
      }
    case 'str':
    default:
      return raw;
  }
}

/**
 * Coerce every declared parameter present on `step` to its spec type.
 * Params not declared on `spec` (extra params on an `allows_extra_params`
 * action) pass through untouched — there is no type to coerce to.
 */
export function coerceParams(step: ClientStep, spec: StepActionSpec): ClientStep {
  const declared = new Map(spec.params.map((param) => [param.name, param]));
  const parameters: Record<string, unknown> = { ...step.parameters };
  for (const [name, paramSpec] of declared) {
    if (!(name in parameters)) continue;
    parameters[name] = coerceParamValue(parameters[name], paramSpec);
  }
  return { ...step, parameters };
}

// ---------------------------------------------------------------------------
// Validation — mirrors flows.step_validation.validate_step_tree
// ---------------------------------------------------------------------------

const TYPE_CHECKS: Record<ParamType, (value: unknown) => boolean> = {
  str: (v) => typeof v === 'string',
  int: (v) => typeof v === 'number' && Number.isInteger(v),
  float: (v) => typeof v === 'number',
  bool: (v) => typeof v === 'boolean',
  dict: (v) => typeof v === 'object' && v !== null && !Array.isArray(v),
  json: () => true,
};

function checkParamValue(
  errors: string[],
  clientId: string,
  paramSpec: ParamSpec,
  value: unknown
): void {
  const isReference =
    paramSpec.accepts_reference && typeof value === 'string' && value.startsWith('@');
  if (!isReference) {
    const checker = TYPE_CHECKS[paramSpec.type] ?? (() => true);
    if (!checker(value)) {
      errors.push(
        `Step '${clientId}': parameter '${paramSpec.name}' is not a valid '${paramSpec.type}' value.`
      );
    }
  }
  if (paramSpec.choices.length > 0 && !paramSpec.choices.some((choice) => choice === value)) {
    errors.push(
      `Step '${clientId}': parameter '${paramSpec.name}' must be one of ${JSON.stringify(paramSpec.choices)}.`
    );
  }
}

function checkStepAgainstSpec(errors: string[], step: ClientStep, spec: StepActionSpec): void {
  if (spec.variable_name_required && !step.variableName.trim()) {
    errors.push(`Step '${step.clientId}': variable_name is required for action '${spec.action}'.`);
  }
  const declared = new Map(spec.params.map((param) => [param.name, param]));
  for (const [name, paramSpec] of declared) {
    if (paramSpec.required && !(name in step.parameters)) {
      errors.push(`Step '${step.clientId}': missing required parameter '${name}'.`);
    }
  }
  for (const [name, value] of Object.entries(step.parameters)) {
    const paramSpec = declared.get(name);
    if (!paramSpec) {
      if (spec.allows_extra_params) continue;
      errors.push(`Step '${step.clientId}': unknown parameter '${name}'.`);
      continue;
    }
    checkParamValue(errors, step.clientId, paramSpec, value);
  }
}

/**
 * Validate an authored (unsaved) step tree against the catalog, returning
 * human-readable problems (empty when the tree is save-safe). Unlike the
 * backend's `validate_step_tree` (which raises on the first violation),
 * this collects every problem it finds so the editor can surface them all
 * at once.
 */
export function validateSteps(steps: ClientStep[], specs: Map<string, StepActionSpec>): string[] {
  const errors: string[] = [];
  if (steps.length === 0) return errors;

  const byId = new Map<string, ClientStep>();
  for (const step of steps) {
    const clientId = step.clientId || '';
    if (!clientId) {
      errors.push('A step has a blank client id.');
      continue;
    }
    if (byId.has(clientId)) {
      errors.push(`Step '${clientId}': duplicate client id.`);
      continue;
    }
    byId.set(clientId, step);
  }

  let rootCount = 0;
  for (const step of steps) {
    const parentId = step.parentClientId;
    if (parentId === null) {
      rootCount += 1;
    } else if (!byId.has(parentId)) {
      errors.push(`Step '${step.clientId}': parent '${parentId}' not found.`);
    }
  }
  if (rootCount !== 1) {
    errors.push(`Step tree must have exactly one root; found ${rootCount}.`);
  }

  for (const step of steps) {
    const visited = new Set<string>([step.clientId]);
    let node: ClientStep = step;
    while (node.parentClientId !== null) {
      const parentId = node.parentClientId;
      if (visited.has(parentId)) {
        errors.push(`Step '${step.clientId}': cycle detected via parent chain.`);
        break;
      }
      visited.add(parentId);
      const parent = byId.get(parentId);
      if (!parent) break; // already reported by the parent-resolution check above
      node = parent;
    }
  }

  for (const step of steps) {
    const spec = specs.get(step.action);
    if (!spec) {
      errors.push(`Step '${step.clientId}': unknown action '${step.action}'.`);
      continue;
    }
    checkStepAgainstSpec(errors, step, spec);
  }

  return errors;
}

// ---------------------------------------------------------------------------
// Server <-> client shape mapping
// ---------------------------------------------------------------------------

/** Map saved `FlowStep`s (pk-addressed) to the client tree shape (clientId-addressed). */
export function fromServerSteps(steps: FlowStep[]): ClientStep[] {
  return steps.map((step) => ({
    clientId: String(step.id),
    parentClientId: step.parent === null ? null : String(step.parent),
    action: step.action,
    variableName: step.variable_name,
    parameters: step.parameters,
  }));
}

/**
 * Map the client tree to the wire shape the flows write endpoints expect.
 * Delegates to `api.ts`'s `toApiStep` (the same per-step mapping used by
 * `createFlow`/`updateFlow`'s full payload) rather than duplicating the
 * snake_case field mapping here.
 */
export function toWirePayload(steps: ClientStep[]): unknown {
  return steps.map(toApiStep);
}

// ---------------------------------------------------------------------------
// Conditional comparison symbols (rendered in the "if <var> <op> <value>" header)
// ---------------------------------------------------------------------------

export const CONDITIONAL_OP_SYMBOLS: Record<string, string> = {
  evaluate_equals: '==',
  evaluate_not_equals: '!=',
  evaluate_less_than: '<',
  evaluate_greater_than: '>',
  evaluate_less_than_or_equals: '<=',
  evaluate_greater_than_or_equals: '>=',
};

/** The comparison symbol for a conditional action; falls back to the raw action name. */
export function conditionalOpSymbol(action: string): string {
  return CONDITIONAL_OP_SYMBOLS[action] ?? action;
}
