/**
 * computeLayout — pure function that converts the API node/option/route
 * tuples into React Flow nodes + edges, applying dagre auto-layout to
 * any node without stored editor_x/y.
 */

import { describe, expect, it } from 'vitest';

import { computeLayout } from '../components/MissionCanvas';
import type {
  GraphProblem,
  MissionNode,
  MissionOption,
  MissionOptionRoute,
  MissionOptionRouteCandidate,
  OutcomeTier,
} from '../types';

const node = (id: number, key: string, overrides: Partial<MissionNode> = {}): MissionNode =>
  ({
    id,
    template: 1,
    key,
    is_entry: false,
    conflict_mode: 'group_vote',
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
    key: '',
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

const TIERS = [
  { id: 1, name: 'Success', success_level: 1 },
  { id: 7, name: 'Failure', success_level: -1 },
] as OutcomeTier[];

const candidate = (id: number, routeId: number, target: number): MissionOptionRouteCandidate =>
  ({ id, route: routeId, target_node: target, weight: 1 }) as MissionOptionRouteCandidate;

/** computeLayout with the new trailing arguments defaulted. */
function layout(
  nodes: MissionNode[],
  options: MissionOption[],
  routes: MissionOptionRoute[],
  extra: {
    candidates?: MissionOptionRouteCandidate[];
    tiers?: OutcomeTier[];
    problems?: GraphProblem[];
  } = {}
) {
  return computeLayout(
    nodes,
    options,
    routes,
    extra.candidates ?? [],
    extra.tiers ?? TIERS,
    extra.problems ?? []
  );
}

describe('computeLayout', () => {
  it('produces one React Flow node per MissionNode', () => {
    const result = layout([node(1, 'a'), node(2, 'b')], [], []);
    expect(result.layoutedNodes).toHaveLength(2);
    const ids = result.layoutedNodes.map((n) => n.id).sort();
    expect(ids).toEqual(['1', '2']);
  });

  it('labels entry nodes with "(entry)"', () => {
    const result = layout([node(1, 'entry', { is_entry: true })], [], []);
    expect(result.layoutedNodes[0].data.label).toBe('entry (entry)');
  });

  it('honors stored editor_x/y for positioned nodes', () => {
    const result = layout([node(1, 'positioned', { editor_x: 100, editor_y: 200 })], [], []);
    expect(result.layoutedNodes[0].position).toEqual({ x: 100, y: 200 });
  });

  it('auto-lays nodes at editor_x=0, editor_y=0 via dagre (not 0/0)', () => {
    // Two unrelated nodes — dagre should place them at distinct positions.
    const result = layout([node(1, 'a'), node(2, 'b')], [], []);
    const positions = result.layoutedNodes.map((n) => `${n.position.x},${n.position.y}`);
    expect(new Set(positions).size).toBe(2);
  });

  it('builds one edge per route with a target', () => {
    const result = layout([node(1, 'src'), node(2, 'dst')], [option(10, 1)], [route(100, 10, 2)]);
    expect(result.layoutedEdges).toHaveLength(1);
    expect(result.layoutedEdges[0]).toMatchObject({
      source: '1',
      target: '2',
    });
  });

  it('draws a route with no target to the Mission ends box', () => {
    const result = layout(
      [node(1, 'src')],
      [option(10, 1, { key: 'dig' })],
      [route(100, 10, null)]
    );
    expect(result.layoutedEdges).toHaveLength(1);
    expect(result.layoutedEdges[0]).toMatchObject({
      source: '1',
      target: 'end',
      label: 'dig · Success',
    });
    const end = result.layoutedNodes.find((n) => n.id === 'end');
    expect(end?.data.label).toBe('Mission ends');
    expect(end?.draggable).toBe(false);
  });

  it('adds no Mission ends box when nothing ends the mission', () => {
    const result = layout([node(1, 'src'), node(2, 'dst')], [option(10, 1)], [route(100, 10, 2)]);
    expect(result.layoutedNodes.find((n) => n.id === 'end')).toBeUndefined();
  });

  it('draws one dashed edge per random-set candidate', () => {
    const result = layout(
      [node(1, 'src'), node(2, 'a'), node(3, 'b')],
      [option(10, 1, { key: 'roll' })],
      [route(100, 10, null, { is_random_set: true, outcome_tier: null })],
      { candidates: [candidate(1, 100, 2), candidate(2, 100, 3)] }
    );
    expect(result.layoutedEdges.map((e) => [e.target, e.label])).toEqual([
      ['2', 'roll · random'],
      ['3', 'roll · random'],
    ]);
    expect(result.layoutedEdges[0].style?.strokeDasharray).toBeTruthy();
    expect(result.layoutedNodes.find((n) => n.id === 'end')).toBeUndefined();
  });

  it('sends a random route with no candidates to Mission ends', () => {
    const result = layout(
      [node(1, 'src')],
      [option(10, 1, { key: 'roll' })],
      [route(100, 10, null, { is_random_set: true, outcome_tier: 7 })]
    );
    expect(result.layoutedEdges.map((e) => [e.target, e.label])).toEqual([
      ['end', 'roll · Failure'],
    ]);
  });

  it('lets a branch target win over a random tier-less route', () => {
    const result = layout(
      [node(1, 'src'), node(2, 'dst'), node(3, 'other')],
      [option(10, 1, { option_kind: 'branch', key: 'go', branch_target: 2 })],
      [route(100, 10, null, { is_random_set: true, outcome_tier: null })],
      { candidates: [candidate(1, 100, 3)] }
    );
    expect(result.layoutedEdges.map((e) => e.target)).toEqual(['2']);
  });

  it('labels regular routes with the option label and tier name', () => {
    const result = layout(
      [node(1, 'src'), node(2, 'dst')],
      [option(10, 1, { authored_ic_framing: 'Climb the wall' })],
      [route(100, 10, 2, { outcome_tier: 7 })]
    );
    expect(result.layoutedEdges[0].label).toBe('Climb the wall · Failure');
  });

  it('labels a tier-less route with the option label alone, falling back to option order', () => {
    const result = layout(
      [node(1, 'src'), node(2, 'dst')],
      [option(10, 1, { order: 3 })],
      [route(100, 10, 2, { outcome_tier: null })]
    );
    expect(result.layoutedEdges[0].label).toBe('option 3');
  });

  it('draws a branch_target edge, and it wins over a tier-less route', () => {
    const result = layout(
      [node(1, 'src'), node(2, 'dst'), node(3, 'other')],
      [option(10, 1, { option_kind: 'branch', key: 'go', branch_target: 2 })],
      [route(100, 10, 3, { outcome_tier: null })]
    );
    expect(result.layoutedEdges.map((e) => [e.target, e.label])).toEqual([['2', 'go']]);
  });

  it('treats a branch option with no route and no branch_target as an ending', () => {
    const result = layout(
      [node(1, 'src')],
      [option(10, 1, { option_kind: 'branch', key: 'leave' })],
      []
    );
    expect(result.layoutedEdges).toMatchObject([{ target: 'end', label: 'leave' }]);
  });

  it('does not treat a check option with no route as an ending', () => {
    const result = layout([node(1, 'src')], [option(10, 1)], []);
    expect(result.layoutedEdges).toHaveLength(0);
  });

  it('draws track success and failure targets', () => {
    const result = layout(
      [
        node(1, 'siege', { track_success_target: 2, track_failure_target: 3 }),
        node(2, 'won'),
        node(3, 'lost'),
      ],
      [],
      []
    );
    expect(result.layoutedEdges.map((e) => [e.target, e.label])).toEqual([
      ['2', 'track success'],
      ['3', 'track failure'],
    ]);
  });

  it('draws no route edge for a check on a track node, and ends an untargeted side', () => {
    const result = layout(
      [
        node(1, 'siege', { track_successes: 2, track_failures: 2, track_success_target: 2 }),
        node(2, 'won'),
      ],
      [option(10, 1, { key: 'storm' })],
      [route(20, 10, null)]
    );
    expect(result.layoutedEdges.map((e) => [e.target, e.label])).toEqual([
      ['2', 'track success'],
      ['end', 'track failure'],
    ]);
  });

  it('drops tiered routes of a branch option and labels an unknown tier by option alone', () => {
    const branch = layout(
      [node(1, 'a'), node(2, 'b')],
      [option(10, 1, { option_kind: 'branch', key: 'fork' })],
      [route(20, 10, 2)]
    );
    expect(branch.layoutedEdges.map((e) => [e.target, e.label])).toEqual([['end', 'fork']]);
    const unknown = layout(
      [node(1, 'a'), node(2, 'b')],
      [option(10, 1, { key: 'roll' })],
      [route(20, 10, 2, { outcome_tier: 99 })]
    );
    expect(unknown.layoutedEdges[0].label).toBe('roll');
  });

  it('marks a node with a problem with a warning prefix and border', () => {
    const problem = {
      kind: 'unreachable_node',
      message: 'x',
      node: 2,
      option: null,
      route: null,
      missing_tiers: [],
    } as GraphProblem;
    const result = layout([node(1, 'a'), node(2, 'b')], [], [], { problems: [problem] });
    expect(result.layoutedNodes[0].data.label).toBe('a');
    expect(result.layoutedNodes[1].data.label).toBe('⚠ b');
    expect(String(result.layoutedNodes[1].style?.border)).toContain('warning');
  });

  it('labels track nodes with "[track N/M]" (#3568)', () => {
    const result = layout([node(1, 'siege', { track_successes: 3, track_failures: 2 })], [], []);
    expect(result.layoutedNodes[0].data.label).toBe('siege [track 3/2]');
  });

  it('does not add a track badge when track_successes is 0', () => {
    const result = layout([node(1, 'plain', { track_successes: 0, track_failures: 0 })], [], []);
    expect(result.layoutedNodes[0].data.label).toBe('plain');
  });
});
