import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

import { TacticalMap } from './TacticalMap';
import type { PositionEdgeLike, PositionNodeLike } from './TacticalMap';
import type { PlayerAction } from '@/scenes/actionTypes';

// React Flow's pane wires a d3-zoom `mousedown` listener for click-drag
// panning. `@testing-library/user-event`'s `click()` dispatches a full
// pointer/mouse sequence (including `mousedown`) whose synthetic `MouseEvent`
// has `view: null` under jsdom, which crashes d3-zoom's internal
// `dragDisable(event.view)` (`Cannot read properties of null (reading
// 'document')`) — an incompatibility between jsdom and d3-zoom, not something
// in this component. `fireEvent.click` dispatches a single `click` event
// (matching what `PositionMapNode`'s `onClick` handler listens for) without
// the `mousedown`/`mouseup` pair, sidestepping the crash entirely.

// jsdom doesn't implement SVG geometry methods (a long-standing, well-known
// gap — https://github.com/jsdom/jsdom/issues/1330), and it constructs SVG
// children like `<text>` as plain `SVGElement` rather than the more specific
// `SVGGraphicsElement`/`SVGTextElement`, so the polyfill has to land on
// `SVGElement.prototype` to actually be picked up by instances. React Flow's
// edge label (`EdgeText`) calls `getBBox()` on its `<text>` element to size
// its background rect; without this stub it throws `getBBox is not a
// function`. Scoped to this file only, since this is the only test in the
// suite that renders a labeled React Flow edge.
if (typeof SVGElement !== 'undefined') {
  const proto = SVGElement.prototype as unknown as { getBBox?: () => DOMRect };
  if (!proto.getBBox) {
    proto.getBBox = () => ({ x: 0, y: 0, width: 0, height: 0 }) as DOMRect;
  }
}

const node = (
  id: number,
  kind = 'feature',
  name = `Position ${id}`,
  overrides: Partial<PositionNodeLike> = {}
): PositionNodeLike => ({
  id,
  name,
  kind,
  elevation_anchor_id: null,
  layout_x: null,
  layout_y: null,
  rampart_element: null,
  rampart_integrity: null,
  rampart_max_integrity: null,
  rampart_crack_state: null,
  ...overrides,
});

const edge = (
  a: number,
  b: number,
  overrides: Partial<PositionEdgeLike> = {}
): PositionEdgeLike => ({
  position_a_id: a,
  position_b_id: b,
  is_passable: true,
  blocks_flight: false,
  gating_challenge_name: null,
  ...overrides,
});

const moveAction = (positionId: number): PlayerAction => ({
  backend: 'registry',
  display_name: `Move to Position ${positionId}`,
  description: '',
  difficulty: null,
  prerequisite_met: true,
  prerequisite_reasons: [],
  check_type: { id: 1, name: 'Standard' },
  action_template: null,
  ref: {
    backend: 'registry',
    challenge_instance_id: null,
    approach_id: null,
    technique_id: null,
    registry_key: 'move_to_position',
    position_id: positionId,
  },
  target_spec: null,
  enhancements: [],
  strain: null,
  action_category: 'physical',
});

describe('TacticalMap', () => {
  it('renders one node per position', () => {
    render(
      <TacticalMap
        nodes={[node(1, 'primary'), node(2)]}
        edges={[edge(1, 2)]}
        occupantsByPosition={new Map()}
        moveActions={[]}
        onDispatchMove={vi.fn()}
      />
    );
    expect(screen.getAllByTestId(/^tactical-map-node-/)).toHaveLength(2);
  });

  it('dispatches the matching move action when clicking a reachable node', () => {
    const onDispatchMove = vi.fn();
    render(
      <TacticalMap
        nodes={[node(1, 'primary'), node(2)]}
        edges={[edge(1, 2)]}
        occupantsByPosition={new Map()}
        moveActions={[moveAction(2)]}
        onDispatchMove={onDispatchMove}
      />
    );
    fireEvent.click(screen.getByTestId('tactical-map-node-2'));
    expect(onDispatchMove).toHaveBeenCalledWith(moveAction(2));
  });

  it('does not dispatch when clicking a node with no matching move action', () => {
    const onDispatchMove = vi.fn();
    render(
      <TacticalMap
        nodes={[node(1, 'primary'), node(2)]}
        edges={[edge(1, 2)]}
        occupantsByPosition={new Map()}
        moveActions={[]}
        onDispatchMove={onDispatchMove}
      />
    );
    fireEvent.click(screen.getByTestId('tactical-map-node-2'));
    expect(onDispatchMove).not.toHaveBeenCalled();
  });

  it('marks a gated edge with the challenge label', () => {
    render(
      <TacticalMap
        nodes={[node(1, 'primary'), node(2)]}
        edges={[edge(1, 2, { gating_challenge_name: 'Cross the Chasm' })]}
        occupantsByPosition={new Map()}
        moveActions={[]}
        onDispatchMove={vi.fn()}
      />
    );
    expect(screen.getByText('Cross the Chasm')).toBeInTheDocument();
  });

  it('renders a rampart ring with element + integrity tooltip on a covered node (#2209)', () => {
    render(
      <TacticalMap
        nodes={[
          node(1, 'primary', 'Position 1', {
            rampart_element: 'Stone',
            rampart_integrity: 18,
            rampart_max_integrity: 24,
            rampart_crack_state: 'intact',
          }),
        ]}
        edges={[]}
        occupantsByPosition={new Map()}
        moveActions={[]}
        onDispatchMove={vi.fn()}
      />
    );
    const nodeEl = screen.getByTestId('tactical-map-node-1');
    expect(nodeEl).toHaveAttribute('title', 'Stone Rampart 18/24');
    expect(nodeEl.querySelector('[data-testid="rampart-ring"]')).toBeInTheDocument();
  });

  it('consumes the click via onGMPlace (#3385) instead of dispatching a move', () => {
    const onDispatchMove = vi.fn();
    const onGMPlace = vi.fn().mockReturnValue(true);
    render(
      <TacticalMap
        nodes={[node(1, 'primary'), node(2)]}
        edges={[edge(1, 2)]}
        occupantsByPosition={new Map()}
        moveActions={[moveAction(2)]}
        onDispatchMove={onDispatchMove}
        onGMPlace={onGMPlace}
      />
    );
    fireEvent.click(screen.getByTestId('tactical-map-node-2'));
    expect(onGMPlace).toHaveBeenCalledWith(2);
    expect(onDispatchMove).not.toHaveBeenCalled();
  });

  it('falls through to move-dispatch when onGMPlace declines the click', () => {
    const onDispatchMove = vi.fn();
    const onGMPlace = vi.fn().mockReturnValue(false);
    render(
      <TacticalMap
        nodes={[node(1, 'primary'), node(2)]}
        edges={[edge(1, 2)]}
        occupantsByPosition={new Map()}
        moveActions={[moveAction(2)]}
        onDispatchMove={onDispatchMove}
        onGMPlace={onGMPlace}
      />
    );
    fireEvent.click(screen.getByTestId('tactical-map-node-2'));
    expect(onGMPlace).toHaveBeenCalledWith(2);
    expect(onDispatchMove).toHaveBeenCalledWith(moveAction(2));
  });

  it('consumes the click via onPickPosition before onGMPlace ever runs (#2206 precedence)', () => {
    const onDispatchMove = vi.fn();
    const onPickPosition = vi.fn().mockReturnValue(true);
    const onGMPlace = vi.fn().mockReturnValue(true);
    render(
      <TacticalMap
        nodes={[node(1, 'primary'), node(2)]}
        edges={[edge(1, 2)]}
        occupantsByPosition={new Map()}
        moveActions={[moveAction(2)]}
        onDispatchMove={onDispatchMove}
        onPickPosition={onPickPosition}
        onGMPlace={onGMPlace}
      />
    );
    fireEvent.click(screen.getByTestId('tactical-map-node-2'));
    expect(onPickPosition).toHaveBeenCalledWith(2);
    expect(onGMPlace).not.toHaveBeenCalled();
    expect(onDispatchMove).not.toHaveBeenCalled();
  });

  it('renders no rampart ring on an uncovered node', () => {
    render(
      <TacticalMap
        nodes={[node(1, 'primary')]}
        edges={[]}
        occupantsByPosition={new Map()}
        moveActions={[]}
        onDispatchMove={vi.fn()}
      />
    );
    const nodeEl = screen.getByTestId('tactical-map-node-1');
    expect(nodeEl.querySelector('[data-testid="rampart-ring"]')).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Tactical overlays (#3555): engagement-lock links, occupant marks, cover.
  // ---------------------------------------------------------------------------

  it('draws an engagement-lock edge between two locked occupants on different nodes', () => {
    render(
      <TacticalMap
        nodes={[node(1, 'primary'), node(2)]}
        edges={[edge(1, 2)]}
        occupantsByPosition={new Map()}
        links={[
          { id: 'lock-5', positionAId: 1, positionBId: 2, label: 'Aerande locked with Knight' },
        ]}
        moveActions={[]}
        onDispatchMove={vi.fn()}
      />
    );
    expect(screen.getByTestId('rf__edge-link-lock-5')).toBeInTheDocument();
    expect(screen.getByLabelText('Aerande locked with Knight')).toBeInTheDocument();
  });

  it('draws no lock edge when the locked pair shares one node', () => {
    render(
      <TacticalMap
        nodes={[node(1, 'primary'), node(2)]}
        edges={[edge(1, 2)]}
        occupantsByPosition={new Map()}
        links={[{ id: 'lock-5', positionAId: 1, positionBId: 1, label: 'same node' }]}
        moveActions={[]}
        onDispatchMove={vi.fn()}
      />
    );
    expect(screen.queryByTestId('rf__edge-link-lock-5')).not.toBeInTheDocument();
  });

  it('renders each occupant mark as a titled glyph on the avatar', () => {
    render(
      <TacticalMap
        nodes={[node(1, 'primary')]}
        edges={[]}
        occupantsByPosition={
          new Map([
            [
              1,
              [
                {
                  name: 'Aerande',
                  marks: [
                    { kind: 'locked' as const, title: 'Aerande: locked with Knight' },
                    { kind: 'covered' as const, title: 'Aerande: covered by Sir Alaric' },
                  ],
                },
                {
                  name: 'Sir Alaric',
                  marks: [{ kind: 'covering' as const, title: 'Sir Alaric: covering Aerande' }],
                },
              ],
            ],
          ])
        }
        moveActions={[]}
        onDispatchMove={vi.fn()}
      />
    );
    const nodeEl = screen.getByTestId('tactical-map-node-1');
    expect(within(nodeEl).getByTestId('occupant-mark-locked')).toHaveAttribute(
      'title',
      'Aerande: locked with Knight'
    );
    expect(within(nodeEl).getByTestId('occupant-mark-covered')).toHaveAttribute(
      'title',
      'Aerande: covered by Sir Alaric'
    );
    expect(within(nodeEl).getByTestId('occupant-mark-covering')).toHaveAttribute(
      'title',
      'Sir Alaric: covering Aerande'
    );
    expect(within(nodeEl).queryByTestId('occupant-mark-cover')).not.toBeInTheDocument();
  });

  it('marks every occupant of a rampart-covered node as behind cover', () => {
    render(
      <TacticalMap
        nodes={[
          node(1, 'feature', 'Wall', {
            rampart_element: 'Stone',
            rampart_integrity: 6,
            rampart_max_integrity: 24,
            rampart_crack_state: 'crumbling',
          }),
          node(2),
        ]}
        edges={[edge(1, 2)]}
        occupantsByPosition={
          new Map([
            [1, [{ name: 'Aerande' }, { name: 'Sir Alaric' }]],
            [2, [{ name: 'Knight' }]],
          ])
        }
        moveActions={[]}
        onDispatchMove={vi.fn()}
      />
    );
    const covered = screen.getByTestId('tactical-map-node-1');
    const glyphs = within(covered).getAllByTestId('occupant-mark-cover');
    expect(glyphs).toHaveLength(2);
    expect(glyphs[0]).toHaveAttribute('title', 'Aerande: behind Stone rampart');
    const open = screen.getByTestId('tactical-map-node-2');
    expect(within(open).queryByTestId('occupant-mark-cover')).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Room-art backdrop (#3556)
  // ---------------------------------------------------------------------------

  it('renders the room art as a backdrop when artUrl is present', () => {
    render(
      <TacticalMap
        nodes={[node(1, 'primary')]}
        edges={[]}
        occupantsByPosition={new Map()}
        moveActions={[]}
        onDispatchMove={vi.fn()}
        artUrl="https://example.test/room-art.png"
      />
    );
    const backdrop = screen.getByTestId('tactical-map-backdrop');
    expect(backdrop).toHaveStyle({
      backgroundImage: 'url(https://example.test/room-art.png)',
    });
  });

  it('renders no backdrop when the room has no art', () => {
    render(
      <TacticalMap
        nodes={[node(1, 'primary')]}
        edges={[]}
        occupantsByPosition={new Map()}
        moveActions={[]}
        onDispatchMove={vi.fn()}
        artUrl={null}
      />
    );
    expect(screen.queryByTestId('tactical-map-backdrop')).not.toBeInTheDocument();
  });
});
