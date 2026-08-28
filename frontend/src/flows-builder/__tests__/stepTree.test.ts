/**
 * stepTree — pure tree ops / coercion / validation for the FlowStepTree
 * editor (#3417 task 10). Mirrors backend rules in
 * `src/flows/step_validation.py` so an authored tree that passes here also
 * passes the server-side `validate_step_tree`.
 */
import { describe, expect, it } from 'vitest';

import {
  addStep,
  childrenOf,
  coerceParams,
  conditionalOpSymbol,
  fromServerSteps,
  moveStep,
  newClientId,
  removeStep,
  toWirePayload,
  validateSteps,
} from '../stepTree';
import type { ClientStep, FlowStep, ParamSpec, StepActionSpec } from '../types';

function paramSpec(
  overrides: Partial<ParamSpec> & { name: string; type: ParamSpec['type'] }
): ParamSpec {
  return {
    required: false,
    description: '',
    accepts_reference: true,
    choices: [],
    ...overrides,
  };
}

function actionSpec(overrides: Partial<StepActionSpec> & { action: string }): StepActionSpec {
  return {
    label: overrides.action,
    description: '',
    variable_name_role: 'flow_variable',
    variable_name_required: false,
    params: [],
    is_conditional: false,
    allows_extra_params: false,
    ...overrides,
  };
}

function step(overrides: Partial<ClientStep> & { clientId: string }): ClientStep {
  return {
    parentClientId: null,
    action: 'set_context_value',
    variableName: '',
    parameters: {},
    ...overrides,
  };
}

const SET_CONTEXT_SPEC = actionSpec({
  action: 'set_context_value',
  variable_name_role: 'object_pk_variable',
  variable_name_required: true,
  params: [
    paramSpec({ name: 'attribute', type: 'str', required: true, accepts_reference: false }),
    paramSpec({ name: 'value', type: 'json', required: false, accepts_reference: false }),
  ],
});

const CALL_SERVICE_SPEC = actionSpec({
  action: 'call_service_function',
  variable_name_role: 'service_function_name',
  variable_name_required: true,
  params: [paramSpec({ name: 'result_variable', type: 'str', accepts_reference: false })],
  allows_extra_params: true,
});

const EVALUATE_EQUALS_SPEC = actionSpec({
  action: 'evaluate_equals',
  variable_name_role: 'flow_variable',
  variable_name_required: true,
  params: [paramSpec({ name: 'value', type: 'str', required: true, accepts_reference: false })],
  is_conditional: true,
});

const MODIFY_SPEC = actionSpec({
  action: 'modify_context_value',
  variable_name_role: 'object_pk_variable',
  variable_name_required: true,
  params: [
    paramSpec({ name: 'attribute', type: 'str', required: true, accepts_reference: false }),
    paramSpec({
      name: 'op',
      type: 'str',
      required: true,
      accepts_reference: false,
      choices: ['set', 'add'],
    }),
  ],
});

describe('newClientId', () => {
  it('returns a unique string each call', () => {
    const a = newClientId();
    const b = newClientId();
    expect(typeof a).toBe('string');
    expect(a).not.toBe(b);
  });
});

describe('childrenOf', () => {
  it('returns direct children of a parent, preserving order', () => {
    const steps = [
      step({ clientId: 'root', parentClientId: null }),
      step({ clientId: 'a', parentClientId: 'root' }),
      step({ clientId: 'b', parentClientId: 'root' }),
      step({ clientId: 'grandchild', parentClientId: 'a' }),
    ];
    expect(childrenOf(steps, 'root').map((s) => s.clientId)).toEqual(['a', 'b']);
    expect(childrenOf(steps, 'a').map((s) => s.clientId)).toEqual(['grandchild']);
    expect(childrenOf(steps, null).map((s) => s.clientId)).toEqual(['root']);
  });
});

describe('addStep', () => {
  it('appends a new step with params prefilled from the spec defaults', () => {
    const next = addStep([], null, 'set_context_value', SET_CONTEXT_SPEC);
    expect(next).toHaveLength(1);
    const added = next[0];
    expect(added.action).toBe('set_context_value');
    expect(added.parentClientId).toBeNull();
    expect(added.variableName).toBe('');
    expect(added.parameters.attribute).toBe('');
    expect(added.parameters.value).toBe('');
    expect(typeof added.clientId).toBe('string');
    expect(added.clientId.length).toBeGreaterThan(0);
  });

  it('appends under the given parent without disturbing existing steps', () => {
    const existing = [step({ clientId: 'root', parentClientId: null })];
    const next = addStep(existing, 'root', 'set_context_value', SET_CONTEXT_SPEC);
    expect(next).toHaveLength(2);
    expect(next[0]).toBe(existing[0]);
    expect(next[1].parentClientId).toBe('root');
  });
});

describe('removeStep', () => {
  it('removes the target step and all of its descendants', () => {
    const steps = [
      step({ clientId: 'root', parentClientId: null }),
      step({ clientId: 'a', parentClientId: 'root' }),
      step({ clientId: 'b', parentClientId: 'root' }),
      step({ clientId: 'a-child', parentClientId: 'a' }),
      step({ clientId: 'a-grandchild', parentClientId: 'a-child' }),
    ];
    const next = removeStep(steps, 'a');
    expect(next.map((s) => s.clientId).sort()).toEqual(['b', 'root']);
  });

  it('leaves the tree unchanged when the target is not found', () => {
    const steps = [step({ clientId: 'root', parentClientId: null })];
    expect(removeStep(steps, 'missing')).toEqual(steps);
  });
});

describe('moveStep', () => {
  it('swaps a step with its previous sibling on "up", leaving non-siblings untouched', () => {
    const steps = [
      step({ clientId: 'root', parentClientId: null }),
      step({ clientId: 'a', parentClientId: 'root' }),
      step({ clientId: 'b', parentClientId: 'root' }),
      step({ clientId: 'c', parentClientId: 'root' }),
    ];
    const next = moveStep(steps, 'b', 'up');
    expect(childrenOf(next, 'root').map((s) => s.clientId)).toEqual(['b', 'a', 'c']);
  });

  it('swaps a step with its next sibling on "down"', () => {
    const steps = [
      step({ clientId: 'root', parentClientId: null }),
      step({ clientId: 'a', parentClientId: 'root' }),
      step({ clientId: 'b', parentClientId: 'root' }),
    ];
    const next = moveStep(steps, 'a', 'down');
    expect(childrenOf(next, 'root').map((s) => s.clientId)).toEqual(['b', 'a']);
  });

  it('is a no-op moving the first sibling up or the last sibling down', () => {
    const steps = [
      step({ clientId: 'root', parentClientId: null }),
      step({ clientId: 'a', parentClientId: 'root' }),
      step({ clientId: 'b', parentClientId: 'root' }),
    ];
    expect(moveStep(steps, 'a', 'up')).toEqual(steps);
    expect(moveStep(steps, 'b', 'down')).toEqual(steps);
  });

  it('never reorders across different parents', () => {
    const steps = [
      step({ clientId: 'root', parentClientId: null }),
      step({ clientId: 'a', parentClientId: 'root' }),
      step({ clientId: 'a-child', parentClientId: 'a' }),
    ];
    // 'a' is an only child of root and 'a-child' is an only child of 'a' —
    // neither has a sibling, so both directions are no-ops.
    expect(moveStep(steps, 'a-child', 'up')).toEqual(steps);
    expect(moveStep(steps, 'a', 'down')).toEqual(steps);
  });
});

describe('coerceParams', () => {
  it('coerces an int param from a numeric string', () => {
    const spec = actionSpec({
      action: 'x',
      params: [paramSpec({ name: 'count', type: 'int', accepts_reference: false })],
    });
    const result = coerceParams(step({ clientId: 'a', parameters: { count: '3' } }), spec);
    expect(result.parameters.count).toBe(3);
  });

  it('coerces a bool param from "true"/"1" strings', () => {
    const spec = actionSpec({
      action: 'x',
      params: [paramSpec({ name: 'flag', type: 'bool', accepts_reference: false })],
    });
    expect(
      coerceParams(step({ clientId: 'a', parameters: { flag: 'true' } }), spec).parameters.flag
    ).toBe(true);
    expect(
      coerceParams(step({ clientId: 'a', parameters: { flag: '1' } }), spec).parameters.flag
    ).toBe(true);
    expect(
      coerceParams(step({ clientId: 'a', parameters: { flag: 'false' } }), spec).parameters.flag
    ).toBe(false);
  });

  it('passes an "@"-prefixed reference through untouched when accepts_reference', () => {
    const spec = actionSpec({
      action: 'x',
      params: [paramSpec({ name: 'count', type: 'int', accepts_reference: true })],
    });
    const result = coerceParams(step({ clientId: 'a', parameters: { count: '@some_var' } }), spec);
    expect(result.parameters.count).toBe('@some_var');
  });

  it('coerces a dict param by JSON.parse, leaving invalid JSON as-is', () => {
    const spec = actionSpec({
      action: 'x',
      params: [paramSpec({ name: 'data', type: 'dict', accepts_reference: false })],
    });
    const good = coerceParams(step({ clientId: 'a', parameters: { data: '{"k": 1}' } }), spec);
    expect(good.parameters.data).toEqual({ k: 1 });
    const bad = coerceParams(step({ clientId: 'a', parameters: { data: 'not json' } }), spec);
    expect(bad.parameters.data).toBe('not json');
  });

  it('leaves parameters not declared on the spec untouched', () => {
    const spec = actionSpec({ action: 'x', allows_extra_params: true, params: [] });
    const result = coerceParams(step({ clientId: 'a', parameters: { extra: 'literal' } }), spec);
    expect(result.parameters.extra).toBe('literal');
  });
});

describe('validateSteps', () => {
  const specs = new Map<string, StepActionSpec>([
    [SET_CONTEXT_SPEC.action, SET_CONTEXT_SPEC],
    [CALL_SERVICE_SPEC.action, CALL_SERVICE_SPEC],
    [EVALUATE_EQUALS_SPEC.action, EVALUATE_EQUALS_SPEC],
    [MODIFY_SPEC.action, MODIFY_SPEC],
  ]);

  it('returns no errors for an empty tree', () => {
    expect(validateSteps([], specs)).toEqual([]);
  });

  it('returns no errors for a valid single-root tree', () => {
    const steps = [
      step({
        clientId: 'root',
        action: 'set_context_value',
        variableName: 'some_obj',
        parameters: { attribute: 'hp' },
      }),
    ];
    expect(validateSteps(steps, specs)).toEqual([]);
  });

  it('flags a tree with two roots', () => {
    const steps = [
      step({
        clientId: 'root1',
        action: 'set_context_value',
        variableName: 'x',
        parameters: { attribute: 'hp' },
      }),
      step({
        clientId: 'root2',
        action: 'set_context_value',
        variableName: 'y',
        parameters: { attribute: 'hp' },
      }),
    ];
    const errors = validateSteps(steps, specs);
    expect(errors.some((e) => /exactly one root/.test(e))).toBe(true);
  });

  it('flags a missing required parameter', () => {
    const steps = [
      step({
        clientId: 'root',
        action: 'set_context_value',
        variableName: 'x',
        parameters: {},
      }),
    ];
    const errors = validateSteps(steps, specs);
    expect(errors.some((e) => e.includes("missing required parameter 'attribute'"))).toBe(true);
  });

  it('flags a step whose parent_client_id does not resolve', () => {
    const steps = [
      step({
        clientId: 'root',
        action: 'set_context_value',
        variableName: 'x',
        parameters: { attribute: 'hp' },
      }),
      step({
        clientId: 'orphan',
        parentClientId: 'nonexistent',
        action: 'set_context_value',
        variableName: 'y',
        parameters: { attribute: 'hp' },
      }),
    ];
    const errors = validateSteps(steps, specs);
    expect(errors.some((e) => /parent .*nonexistent.* not found/i.test(e))).toBe(true);
  });

  it('flags an unknown action', () => {
    const steps = [step({ clientId: 'root', action: 'not_a_real_action' })];
    const errors = validateSteps(steps, specs);
    expect(errors.some((e) => e.includes("unknown action 'not_a_real_action'"))).toBe(true);
  });

  it('requires variable_name when the spec requires it', () => {
    const steps = [
      step({
        clientId: 'root',
        action: 'set_context_value',
        variableName: '',
        parameters: { attribute: 'hp' },
      }),
    ];
    const errors = validateSteps(steps, specs);
    expect(errors.some((e) => e.includes('variable_name is required'))).toBe(true);
  });

  it('rejects an unknown parameter unless the spec allows extra params', () => {
    const steps = [
      step({
        clientId: 'root',
        action: 'set_context_value',
        variableName: 'x',
        parameters: { attribute: 'hp', bogus: 1 },
      }),
    ];
    const errors = validateSteps(steps, specs);
    expect(errors.some((e) => e.includes("unknown parameter 'bogus'"))).toBe(true);
  });

  it('allows unknown parameters when the spec allows extra params', () => {
    const steps = [
      step({
        clientId: 'root',
        action: 'call_service_function',
        variableName: 'some_function',
        parameters: { target: '@actor' },
      }),
    ];
    expect(validateSteps(steps, specs)).toEqual([]);
  });

  it('flags a type mismatch, exempting an "@"-reference on an accepts_reference param', () => {
    const spec = new Map<string, StepActionSpec>([
      [
        'x',
        actionSpec({
          action: 'x',
          params: [paramSpec({ name: 'count', type: 'int', accepts_reference: true })],
        }),
      ],
    ]);
    const bad = [step({ clientId: 'root', action: 'x', parameters: { count: 'nope' } })];
    expect(validateSteps(bad, spec).some((e) => e.includes("not a valid 'int' value"))).toBe(true);
    const okRef = [step({ clientId: 'root', action: 'x', parameters: { count: '@some_var' } })];
    expect(validateSteps(okRef, spec)).toEqual([]);
  });

  it('flags a value outside the declared choices', () => {
    const steps = [
      step({
        clientId: 'root',
        action: 'modify_context_value',
        variableName: 'x',
        parameters: { attribute: 'hp', op: 'not_a_choice' },
      }),
    ];
    const errors = validateSteps(steps, specs);
    expect(errors.some((e) => e.includes('must be one of'))).toBe(true);
  });
});

describe('fromServerSteps / toWirePayload round-trip', () => {
  it('maps server pks to clientId strings and back to the wire shape', () => {
    const serverSteps: FlowStep[] = [
      {
        id: 10,
        parent: null,
        action: 'set_context_value',
        variable_name: 'root_var',
        parameters: { attribute: 'hp' },
      },
      {
        id: 11,
        parent: 10,
        action: 'evaluate_equals',
        variable_name: 'root_var',
        parameters: { value: '5' },
      },
    ];
    const clientSteps = fromServerSteps(serverSteps);
    expect(clientSteps).toHaveLength(2);
    expect(clientSteps[0].clientId).toBe('10');
    expect(clientSteps[0].parentClientId).toBeNull();
    expect(clientSteps[1].clientId).toBe('11');
    expect(clientSteps[1].parentClientId).toBe('10');

    const wire = toWirePayload(clientSteps) as Record<string, unknown>[];
    expect(wire).toEqual([
      {
        client_id: '10',
        parent_client_id: null,
        action: 'set_context_value',
        variable_name: 'root_var',
        parameters: { attribute: 'hp' },
      },
      {
        client_id: '11',
        parent_client_id: '10',
        action: 'evaluate_equals',
        variable_name: 'root_var',
        parameters: { value: '5' },
      },
    ]);
  });
});

describe('conditionalOpSymbol', () => {
  it('maps every conditional action to its comparison symbol', () => {
    expect(conditionalOpSymbol('evaluate_equals')).toBe('==');
    expect(conditionalOpSymbol('evaluate_not_equals')).toBe('!=');
    expect(conditionalOpSymbol('evaluate_less_than')).toBe('<');
    expect(conditionalOpSymbol('evaluate_greater_than')).toBe('>');
    expect(conditionalOpSymbol('evaluate_less_than_or_equals')).toBe('<=');
    expect(conditionalOpSymbol('evaluate_greater_than_or_equals')).toBe('>=');
  });

  it('falls back to the raw action name for a non-conditional action', () => {
    expect(conditionalOpSymbol('set_context_value')).toBe('set_context_value');
  });
});
