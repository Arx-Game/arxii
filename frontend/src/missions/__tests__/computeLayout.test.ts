/**
 * computeLayout — pure function that converts the API node/option/route
 * tuples into React Flow nodes + edges, applying dagre auto-layout to
 * any node without stored editor_x/y.
 */

import { describe, expect, it } from 'vitest';

import { computeLayout } from '../components/MissionCanvas';
import type { MissionNode, MissionOption, MissionOptionRoute } from '../types';

const node = (id: number, key: string, overrides: Partial<MissionNode> = {}): MissionNode =>
  ({
    id,
    template: 1,
    key,
    is_entry: false,
    conflict_mode: 'coinflip',
    joint_combine: null,
    joint_count: null,
    allowed_riders: [],
    deny_all_riders: false,
    editor_x: 0,
    editor_y: 0,
    flavor_text: '',
    flavor_text_needs_rewrite: false,
    ...overrides,
  }) as unknown as MissionNode;

const option = (
  id: number,
  nodeId: number,
  overrides: Partial<MissionOption> = {}
): MissionOption =>
  ({
    id,
    node: nodeId,
    order: 1,
    option_kind: 'check',
    source_kind: 'authored',
    visibility_rule: {},
    authored_check_type: null,
    authored_base_risk: 0,
    authored_ic_framing: '',
    authored_ic_framing_needs_rewrite: false,
    branch_target: null,
    challenge: null,
    ...overrides,
  }) as unknown as MissionOption;

const route = (
  id: number,
  optionId: number,
  targetNodeId: number | null,
  overrides: Partial<MissionOptionRoute> = {}
): MissionOptionRoute =>
  ({
    id,
    option: optionId,
    outcome_tier: 1,
    target_node: targetNodeId,
    is_random_set: false,
    consequence: null,
    outcome_text: '',
    outcome_text_needs_rewrite: false,
    ...overrides,
  }) as unknown as MissionOptionRoute;

describe('computeLayout', () => {
  it('produces one React Flow node per MissionNode', () => {
    const result = computeLayout([node(1, 'a'), node(2, 'b')], [], []);
    expect(result.layoutedNodes).toHaveLength(2);
    const ids = result.layoutedNodes.map((n) => n.id).sort();
    expect(ids).toEqual(['1', '2']);
  });

  it('labels entry nodes with "(entry)"', () => {
    const result = computeLayout([node(1, 'entry', { is_entry: true })], [], []);
    expect(result.layoutedNodes[0].data.label).toBe('entry (entry)');
  });

  it('honors stored editor_x/y for positioned nodes', () => {
    const result = computeLayout([node(1, 'positioned', { editor_x: 100, editor_y: 200 })], [], []);
    expect(result.layoutedNodes[0].position).toEqual({ x: 100, y: 200 });
  });

  it('auto-lays nodes at editor_x=0, editor_y=0 via dagre (not 0/0)', () => {
    // Two unrelated nodes — dagre should place them at distinct positions.
    const result = computeLayout([node(1, 'a'), node(2, 'b')], [], []);
    const positions = result.layoutedNodes.map((n) => `${n.position.x},${n.position.y}`);
    expect(new Set(positions).size).toBe(2);
  });

  it('builds one edge per route with a target', () => {
    const result = computeLayout(
      [node(1, 'src'), node(2, 'dst')],
      [option(10, 1)],
      [route(100, 10, 2)]
    );
    expect(result.layoutedEdges).toHaveLength(1);
    expect(result.layoutedEdges[0]).toMatchObject({
      source: '1',
      target: '2',
    });
  });

  it('skips routes with null target_node (un-wired routes)', () => {
    const result = computeLayout([node(1, 'src')], [option(10, 1)], [route(100, 10, null)]);
    expect(result.layoutedEdges).toHaveLength(0);
  });

  it('labels random-set routes with "random"', () => {
    const result = computeLayout(
      [node(1, 'src'), node(2, 'dst')],
      [option(10, 1)],
      [route(100, 10, 2, { is_random_set: true })]
    );
    expect(result.layoutedEdges[0].label).toBe('random');
  });

  it('labels regular routes with their outcome tier id', () => {
    const result = computeLayout(
      [node(1, 'src'), node(2, 'dst')],
      [option(10, 1)],
      [route(100, 10, 2, { outcome_tier: 7 })]
    );
    expect(result.layoutedEdges[0].label).toBe('t7');
  });
});
